#!/usr/bin/env python3
"""
Conversation viewer for dual-agent chat system.
Displays saved conversations in a readable format.
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def wait_for_keypress():
    """Wait for user to press any key to continue."""
    try:
        # For Unix/Mac
        import termios
        import tty
        
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except (ImportError, AttributeError):
        # Fallback for Windows or if termios not available
        input()  # Just use regular input


def format_conversation(filepath: str, show_metadata: bool = True, interactive: bool = False):
    """
    Display a conversation in a readable format.
    
    Args:
        filepath: Path to the conversation JSON file
        show_metadata: Whether to show scenario metadata
        interactive: If True, wait for keypress after each turn
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Display metadata
        if show_metadata:
            print("\n" + "="*70)
            print(f"📖 {data['scenario']}")
            print("="*70)
            print(f"🕐 Date: {data['timestamp']}")
            print(f"👥 Characters: {data['characters']['a']} & {data['characters']['b']}")
            print(f"💬 Total Turns: {len(data['conversation'])}")
            print("="*70 + "\n")
        
        # Display conversation
        total_turns = len(data['conversation'])
        for i, turn in enumerate(data['conversation']):
            turn_num = turn['turn']
            name = turn['name']
            message = turn['message']
            
            # Format turn header
            if turn_num == 0:
                print(f"[Initial] {name}:")
            else:
                print(f"[Turn {turn_num}] {name}:")
            
            # Indent and wrap message
            lines = message.split('\n')
            for line in lines:
                print(f"  {line}")
            print()  # Blank line between turns
            
            # Wait for keypress in interactive mode (except after last turn)
            if interactive and i < total_turns - 1:
                print("💬 Press any key to continue...", end='', flush=True)
                wait_for_keypress()
                print("\r" + " " * 40 + "\r", end='')  # Clear the prompt line
        
        print("="*70)
        print("✅ End of conversation\n")
        
    except FileNotFoundError:
        print(f"❌ File not found: {filepath}")
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in file: {filepath}")
    except Exception as e:
        print(f"❌ Error reading conversation: {e}")


def list_conversations(directory: str = "conversations"):
    """List all saved conversations."""
    conv_dir = Path(directory)
    
    if not conv_dir.exists():
        print(f"❌ Directory not found: {directory}")
        return []
    
    json_files = sorted(conv_dir.glob("*.json"), reverse=True)
    
    if not json_files:
        print(f"📭 No conversations found in {directory}/")
        return []
    
    print("\n" + "="*70)
    print("📚 SAVED CONVERSATIONS")
    print("="*70)
    
    conversations = []
    for i, filepath in enumerate(json_files, 1):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            scenario = data.get('scenario', 'Unknown')
            timestamp = data.get('timestamp', 'Unknown')
            num_turns = len(data.get('conversation', []))
            
            print(f"{i}. {filepath.name}")
            print(f"   Scenario: {scenario}")
            print(f"   Time: {timestamp}")
            print(f"   Turns: {num_turns}")
            print()
            
            conversations.append(filepath)
            
        except Exception as e:
            print(f"{i}. {filepath.name} (Error: {e})")
    
    print("="*70 + "\n")
    return conversations


def export_to_markdown(filepath: str, output_file: str = None):
    """Export conversation to Markdown format."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if output_file is None:
            output_file = Path(filepath).stem + ".md"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            # Write header
            f.write(f"# {data['scenario']}\n\n")
            f.write(f"**Date:** {data['timestamp']}  \n")
            f.write(f"**Characters:** {data['characters']['a']} & {data['characters']['b']}  \n")
            f.write(f"**Turns:** {len(data['conversation'])}  \n\n")
            f.write("---\n\n")
            
            # Write conversation
            for turn in data['conversation']:
                turn_num = turn['turn']
                name = turn['name']
                message = turn['message']
                
                if turn_num == 0:
                    f.write(f"## Initial Message\n\n")
                else:
                    f.write(f"## Turn {turn_num}\n\n")
                
                f.write(f"**{name}:**\n\n")
                f.write(f"{message}\n\n")
                f.write("---\n\n")
        
        print(f"✅ Exported to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error exporting: {e}")


def main():
    """Main entry point."""
    if len(sys.argv) == 1:
        # No arguments - list all conversations
        conversations = list_conversations()
        
        if conversations:
            print("To view a conversation, run:")
            print("  python view_conversation.py <number>")
            print("  python view_conversation.py <filename>")
            print("\nInteractive mode (turn-by-turn):")
            print("  python view_conversation.py <number> -i")
            print("  python view_conversation.py <filename> --interactive")
            print("\nTo export to Markdown:")
            print("  python view_conversation.py <filename> --markdown")
    
    elif sys.argv[1] == "--help" or sys.argv[1] == "-h":
        print("Usage:")
        print("  python view_conversation.py                    # List all conversations")
        print("  python view_conversation.py <number>           # View conversation by number")
        print("  python view_conversation.py <filename>         # View specific file")
        print("  python view_conversation.py <number> -i        # Interactive mode (turn-by-turn)")
        print("  python view_conversation.py <filename> --interactive  # Interactive mode")
        print("  python view_conversation.py <filename> --md    # Export to Markdown")
        print("  python view_conversation.py --latest           # View most recent")
        print("  python view_conversation.py --latest -i        # View most recent interactively")
    
    elif sys.argv[1] == "--latest":
        # View most recent conversation
        conversations = list(Path("conversations").glob("*.json"))
        if conversations:
            latest = max(conversations, key=lambda p: p.stat().st_mtime)
            # Check for interactive flag
            interactive = len(sys.argv) > 2 and sys.argv[2] in ["-i", "--interactive"]
            format_conversation(str(latest), interactive=interactive)
        else:
            print("📭 No conversations found")
    
    elif sys.argv[1].isdigit():
        # View by number
        conversations = list_conversations()
        num = int(sys.argv[1])
        if 1 <= num <= len(conversations):
            # Check for interactive flag
            interactive = len(sys.argv) > 2 and sys.argv[2] in ["-i", "--interactive"]
            format_conversation(str(conversations[num - 1]), show_metadata=True, interactive=interactive)
        else:
            print(f"❌ Invalid number. Choose 1-{len(conversations)}")
    
    else:
        # View specific file
        filepath = sys.argv[1]
        
        # Check flags
        interactive = False
        export_md = False
        
        if len(sys.argv) > 2:
            if sys.argv[2] in ["--md", "--markdown"]:
                export_md = True
            elif sys.argv[2] in ["-i", "--interactive"]:
                interactive = True
        
        if export_md:
            export_to_markdown(filepath)
        else:
            format_conversation(filepath, interactive=interactive)


if __name__ == "__main__":
    main()
