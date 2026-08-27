"""Stage orchestration + resume logic."""

from __future__ import annotations

import copy
import json
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from . import comfy_client, drawthings_client
from .chunking import Chunk, split_into_chunks
from .config import RunConfig
from .manifest import RunManifest, sha256_text
from .prompt_enhance import enhance_description
from .prompt_gen import build_prompt
from .scene_selection import max_scenes_per_chunk, reconcile_scenes, select_scene_candidates
from .story_bible import merge_bible, summarize_chunk


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_chunk_stage(config: RunConfig, manifest: RunManifest, story_text: str) -> list[Chunk]:
    out_path = config.out_dir / "chunks.json"
    if not manifest.should_run_stage(config, "chunk") and out_path.exists():
        print("[chunk] up to date, reusing chunks.json")
        raw = _read_json(out_path)
        return [Chunk(**c) for c in raw]

    print(f"[chunk] splitting story ({len(story_text)} chars, budget {config.chunk_budget_chars})...")
    chunks = split_into_chunks(story_text, config.chunk_budget_chars)
    _write_json(out_path, [asdict(c) for c in chunks])
    manifest.mark_stage_done("chunk", manifest.stage_input_hash(config, "chunk"), out_path.name)
    print(f"[chunk] produced {len(chunks)} chunk(s)")
    return chunks


def run_bible_stage(config: RunConfig, manifest: RunManifest, chunks: list[Chunk]) -> dict:
    out_path = config.out_dir / "story_bible.json"
    if not manifest.should_run_stage(config, "bible") and out_path.exists():
        print("[bible] up to date, reusing story_bible.json")
        return _read_json(out_path)

    print(f"[bible] summarizing {len(chunks)} section(s) ({config.parallel_chunks} in parallel)...")
    results: dict[int, dict] = {}
    workers = max(1, min(config.parallel_chunks, len(chunks)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(summarize_chunk, chunk, config.llm_url, config.llm_model, api_key=config.llm_api_key): chunk
            for chunk in chunks
        }
        done = 0
        for future in as_completed(futures):
            chunk = futures[future]
            results[chunk.index] = future.result()
            done += 1
            print(f"    section {chunk.index + 1}/{len(chunks)} done ({done}/{len(chunks)})...")
    summaries = [results[i] for i in sorted(results)]

    print("[bible] merging into story bible...")
    bible = merge_bible(summaries, config.llm_url, config.llm_model, api_key=config.llm_api_key)
    _write_json(out_path, bible)
    manifest.mark_stage_done("bible", manifest.stage_input_hash(config, "bible"), out_path.name)
    print(f"[bible] {len(bible.get('characters', []))} character(s), {len(bible.get('settings', []))} setting(s)")
    return bible


def run_scenes_stage(config: RunConfig, manifest: RunManifest, chunks: list[Chunk], bible: dict) -> list[dict]:
    out_path = config.out_dir / "scenes.json"
    if not manifest.should_run_stage(config, "scenes") and out_path.exists():
        print("[scenes] up to date, reusing scenes.json")
        return _read_json(out_path)

    max_per_chunk = max_scenes_per_chunk(len(chunks))
    print(f"[scenes] selecting illustration points across {len(chunks)} section(s) ({config.parallel_chunks} in parallel, up to {max_per_chunk}/section)...")
    results: dict[int, list[dict]] = {}
    workers = max(1, min(config.parallel_chunks, len(chunks)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(select_scene_candidates, chunk, bible, config.llm_url, config.llm_model, max_per_chunk, api_key=config.llm_api_key): chunk
            for chunk in chunks
        }
        for future in as_completed(futures):
            chunk = futures[future]
            candidates = future.result()
            results[chunk.index] = candidates
            print(f"    section {chunk.index + 1}/{len(chunks)}: {len(candidates)} candidate(s)")
    all_candidates = [c for i in sorted(results) for c in results[i]]

    scenes = reconcile_scenes(all_candidates, config.num_scenes)
    if config.num_scenes is not None and len(scenes) < config.num_scenes:
        print(
            f"[scenes] NOTE: only {len(scenes)} grounded scene(s) found, "
            f"fewer than requested --num-scenes {config.num_scenes} (not inventing ungrounded scenes).",
            file=sys.stderr,
        )
    _write_json(out_path, scenes)
    manifest.mark_stage_done("scenes", manifest.stage_input_hash(config, "scenes"), out_path.name)
    print(f"[scenes] finalized {len(scenes)} scene(s)")
    return scenes


def run_prompts_stage(config: RunConfig, manifest: RunManifest, scenes: list[dict], bible: dict) -> list[dict]:
    out_path = config.out_dir / "prompts.json"
    if not manifest.should_run_stage(config, "prompts") and out_path.exists():
        print("[prompts] up to date, reusing prompts.json")
        return _read_json(out_path)

    if config.enhance_prompts:
        print(f"[prompts] enhancing {len(scenes)} scene description(s) ({config.parallel_chunks} in parallel)...")
        workers = max(1, min(config.parallel_chunks, len(scenes)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    enhance_description, scene["description"], config.prompt_style,
                    config.llm_url, config.llm_model,
                    api_key=config.llm_api_key,
                    num_characters=len(scene.get("characters_present", [])),
                ): i
                for i, scene in enumerate(scenes)
            }
            enhanced = [None] * len(scenes)
            done = 0
            for future in as_completed(futures):
                i = futures[future]
                enhanced[i] = future.result()
                done += 1
                print(f"    scene {done}/{len(scenes)} enhanced")
        scenes = [{**scene, "description": enhanced[i]} for i, scene in enumerate(scenes)]

    print(f"[prompts] composing {len(scenes)} prompt(s) (style={config.prompt_style})...")
    prompts = [
        build_prompt(
            scene, bible,
            global_negative_prompt=config.negative_prompt,
            seed=config.seed,
            style=config.prompt_style,
        )
        for scene in scenes
    ]
    _write_json(out_path, prompts)
    manifest.mark_stage_done("prompts", manifest.stage_input_hash(config, "prompts"), out_path.name)
    return prompts


def _run_images_comfy(config: RunConfig, manifest: RunManifest, prompts: list[dict]) -> None:
    if config.workflow_file is None:
        raise SystemExit("--workflow-file is required to run the images stage with --backend comfy")

    images_dir = config.out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    workflow_template = _read_json(config.workflow_file)
    prompt_node_id = config.prompt_node_id or comfy_client.find_positive_prompt_node(workflow_template)
    neg_node_id = config.neg_prompt_node_id or comfy_client.find_negative_prompt_node(workflow_template, prompt_node_id)
    print(f"[images] backend=comfy, positive node: {prompt_node_id}, negative node: {neg_node_id or '(none)'}")

    client_id = str(uuid.uuid4())
    total = len(prompts)
    for i, scene in enumerate(prompts, start=1):
        scene_id = scene["id"]
        current_status = manifest.image_status(scene_id)
        if current_status == "done" and not config.force:
            print(f"  ({i}/{total}) scene {scene_id}: already done, skipping")
            continue

        width, height = config.resolve_scene_size(scene)

        workflow = copy.deepcopy(workflow_template)
        workflow[prompt_node_id]["inputs"]["text"] = scene["prompt"]
        if neg_node_id and scene.get("negative_prompt"):
            workflow[neg_node_id]["inputs"]["text"] = scene["negative_prompt"]
        comfy_client.apply_generation_params(
            workflow,
            seed=scene.get("seed", config.seed),
            steps=config.steps,
            cfg_scale=config.cfg_scale,
            width=width,
            height=height,
        )

        base_filename = f"{scene_id}_{comfy_client.slugify(scene.get('anchor', scene['prompt']))}"
        print(f"  ({i}/{total}) {base_filename} [{scene.get('orientation', 'square')}] :: {scene['prompt'][:70]}...")

        try:
            prompt_id = comfy_client.submit_workflow(config.comfy_url, workflow, client_id)
            history_entry = comfy_client.wait_for_result(config.comfy_url, prompt_id)
            saved = comfy_client.download_outputs(config.comfy_url, history_entry, images_dir, base_filename)
            for p in saved:
                print(f"      saved -> {p}")
            manifest.set_image_status(scene_id, "done")
        except Exception as e:
            print(f"      FAILED: {e}", file=sys.stderr)
            manifest.set_image_status(scene_id, "failed")
            continue


def _run_images_drawthings(config: RunConfig, manifest: RunManifest, prompts: list[dict]) -> None:
    print(f"[images] backend=drawthings, server: {config.drawthings_url}")

    images_dir = config.out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    total = len(prompts)
    for i, scene in enumerate(prompts, start=1):
        scene_id = scene["id"]
        current_status = manifest.image_status(scene_id)
        if current_status == "done" and not config.force:
            print(f"  ({i}/{total}) scene {scene_id}: already done, skipping")
            continue

        width, height = config.resolve_scene_size(scene)

        base_filename = f"{scene_id}_{comfy_client.slugify(scene.get('anchor', scene['prompt']))}"
        print(f"  ({i}/{total}) {base_filename} [{scene.get('orientation', 'square')}] :: {scene['prompt'][:70]}...")

        try:
            images = drawthings_client.generate_images(
                config.drawthings_url,
                prompt=scene["prompt"],
                negative_prompt=scene.get("negative_prompt", ""),
                seed=scene.get("seed", config.seed),
                steps=config.steps,
                cfg_scale=config.cfg_scale,
                width=width,
                height=height,
            )
            saved = drawthings_client.save_images(images, images_dir, base_filename)
            for p in saved:
                print(f"      saved -> {p}")
            manifest.set_image_status(scene_id, "done")
        except Exception as e:
            print(f"      FAILED: {e}", file=sys.stderr)
            manifest.set_image_status(scene_id, "failed")
            continue


def run_images_stage(config: RunConfig, manifest: RunManifest, prompts: list[dict]) -> None:
    if config.backend == "drawthings":
        _run_images_drawthings(config, manifest, prompts)
    else:
        _run_images_comfy(config, manifest, prompts)


def run_pipeline(config: RunConfig) -> None:
    config.out_dir.mkdir(parents=True, exist_ok=True)
    manifest = RunManifest(config.out_dir / "manifest.json")

    story_text = config.story_file.read_text(encoding="utf-8")
    manifest.set_story_hash(sha256_text(story_text))

    if config.force_from:
        manifest.invalidate_from(config.force_from)

    chunks = run_chunk_stage(config, manifest, story_text)
    if config.only_stage == "chunk":
        return

    bible = run_bible_stage(config, manifest, chunks)
    if config.only_stage == "bible":
        return

    scenes = run_scenes_stage(config, manifest, chunks, bible)
    if config.only_stage == "scenes":
        return

    prompts = run_prompts_stage(config, manifest, scenes, bible)
    if config.only_stage == "prompts":
        return

    run_images_stage(config, manifest, prompts)
    print("Done.")
