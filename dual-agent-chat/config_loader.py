"""
Configuration loader for dual agent chat system.
Loads and validates app.json and associated markdown files.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any


class ConfigLoader:
    """Handles loading and validation of configuration files."""
    
    def __init__(self, config_path: str = "app.json"):
        """
        Initialize the configuration loader.
        
        Args:
            config_path: Path to the app.json configuration file
        """
        self.config_path = config_path
        self.base_dir = Path(config_path).parent
        self.config: Dict[str, Any] = {}
        self.world_info: str = ""
        self.character_a_info: str = ""
        self.character_b_info: str = ""
        
    def load(self) -> bool:
        """
        Load all configuration and content files.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Load JSON configuration
            if not self._load_json_config():
                return False
            
            # Load markdown files
            if not self._load_markdown_files():
                return False
            
            # Validate configuration
            if not self._validate_config():
                return False
            
            print(f"✅ Configuration loaded successfully: {self.config['scenario_name']}")
            return True
            
        except Exception as e:
            print(f"❌ Error loading configuration: {e}")
            return False
    
    def _load_json_config(self) -> bool:
        """Load the JSON configuration file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            return True
        except FileNotFoundError:
            print(f"❌ Configuration file not found: {self.config_path}")
            return False
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in configuration file: {e}")
            return False
    
    def _load_markdown_files(self) -> bool:
        """Load all markdown content files."""
        try:
            # Load world info
            world_path = self.base_dir / self.config['world_info_file']
            with open(world_path, 'r', encoding='utf-8') as f:
                self.world_info = f.read().strip()
            
            # Load character A
            char_a_path = self.base_dir / self.config['character_a_file']
            with open(char_a_path, 'r', encoding='utf-8') as f:
                self.character_a_info = f.read().strip()
            
            # Load character B
            char_b_path = self.base_dir / self.config['character_b_file']
            with open(char_b_path, 'r', encoding='utf-8') as f:
                self.character_b_info = f.read().strip()
            
            return True
            
        except FileNotFoundError as e:
            print(f"❌ Markdown file not found: {e}")
            return False
        except Exception as e:
            print(f"❌ Error reading markdown files: {e}")
            return False
    
    def _validate_config(self) -> bool:
        """Validate that all required configuration fields are present."""
        required_fields = [
            'scenario_name',
            'world_info_file',
            'character_a_file',
            'character_b_file',
            'character_a_name',
            'character_b_name',
            'starting_character',
            'llm_config',
            'conversation_config'
        ]
        
        for field in required_fields:
            if field not in self.config:
                print(f"❌ Missing required field in configuration: {field}")
                return False
        
        # Validate starting character
        if self.config['starting_character'] not in ['a', 'b']:
            print("❌ starting_character must be 'a' or 'b'")
            return False
        
        # Validate LLM config
        llm_required = ['api_base_url', 'model']
        for field in llm_required:
            if field not in self.config['llm_config']:
                print(f"❌ Missing required field in llm_config: {field}")
                return False
        
        return True
    
    def get_character_info(self, character: str) -> str:
        """
        Get character information by character identifier.
        
        Args:
            character: 'a' or 'b'
            
        Returns:
            Character information as string
        """
        if character == 'a':
            return self.character_a_info
        elif character == 'b':
            return self.character_b_info
        else:
            raise ValueError(f"Invalid character: {character}")
    
    def get_character_name(self, character: str) -> str:
        """
        Get character name by character identifier.
        
        Args:
            character: 'a' or 'b'
            
        Returns:
            Character name
        """
        if character == 'a':
            return self.config['character_a_name']
        elif character == 'b':
            return self.config['character_b_name']
        else:
            raise ValueError(f"Invalid character: {character}")
    
    def display_config_summary(self):
        """Display a summary of loaded configuration."""
        print("\n" + "="*60)
        print(f"Scenario: {self.config['scenario_name']}")
        print("="*60)
        print(f"Character A: {self.config['character_a_name']}")
        print(f"Character B: {self.config['character_b_name']}")
        print(f"Starting: Character {self.config['starting_character'].upper()}")
        print(f"Model: {self.config['llm_config']['model']}")
        print(f"Max Turns: {self.config['conversation_config']['max_turns']}")
        print("="*60 + "\n")


# Test function
if __name__ == "__main__":
    loader = ConfigLoader("app.json")
    if loader.load():
        loader.display_config_summary()
        print("World Info Preview:")
        print(loader.world_info[:200] + "...\n")
        print("Character A Preview:")
        print(loader.character_a_info[:200] + "...\n")
