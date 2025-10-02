"""
Main application for dual agent chat system.
Orchestrates the conversation between two AI agents.
"""

import os
import sys
import json
import select
import termios
import tty
from datetime import datetime
from pathlib import Path
from config_loader import ConfigLoader
from message_manager import MessageManager
from llm_client import LLMClient


class DualAgentChat:
    """Main application class for dual agent conversations."""
    
    def __init__(self, config_path: str = "app.json", continue_from: str = None, 
                 interrupt_timeout: int = None, interactive_mode: bool = False):
        """
        Initialize the dual agent chat application.
        
        Args:
            config_path: Path to the configuration file
            continue_from: Path to existing conversation JSON to continue from
            interrupt_timeout: Timeout in seconds for SPACE interrupt (overrides config)
            interactive_mode: Start in interactive mode (always prompt for messages)
        """
        self.config_path = config_path
        self.config_loader = None
        self.message_manager = None
        self.llm_client = None
        self.conversation_log = []
        self.conversation_filepath = None  # Track the file we're appending to
        self.continue_from = continue_from  # Path to conversation to continue
        self.existing_conversation_data = None  # Loaded conversation data
        self.interrupt_timeout = interrupt_timeout  # CLI override for timeout
        self.interactive_mode = interactive_mode  # Whether in interactive mode
        self.auto_mode = not interactive_mode  # Track auto vs interactive
        
    def initialize(self) -> bool:
        """
        Initialize all components.
        
        Returns:
            True if successful, False otherwise
        """
        print("\n🚀 Initializing Dual Agent Chat System...")
        print("="*60)
        
        # Load configuration
        self.config_loader = ConfigLoader(self.config_path)
        if not self.config_loader.load():
            return False
        
        self.config_loader.display_config_summary()
        
        # Initialize message manager
        self.message_manager = MessageManager(
            world_info=self.config_loader.world_info,
            char_a_info=self.config_loader.character_a_info,
            char_b_info=self.config_loader.character_b_info,
            char_a_name=self.config_loader.config['character_a_name'],
            char_b_name=self.config_loader.config['character_b_name']
        )
        
        # Initialize LLM client
        self.llm_client = LLMClient(self.config_loader.config['llm_config'])
        
        # Set interrupt timeout (CLI override or config, default 5 seconds)
        if self.interrupt_timeout is not None:
            self.timeout = self.interrupt_timeout
        else:
            self.timeout = self.config_loader.config.get('conversation_config', {}).get('interrupt_timeout', 5)
        
        print(f"⏱️  Interrupt timeout: {self.timeout} seconds")
        print("✅ All components initialized\n")
        return True
    
    def load_existing_conversation(self) -> bool:
        """
        Load an existing conversation to continue from.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.continue_from:
            return True  # Nothing to load
        
        print(f"\n📂 Loading existing conversation: {self.continue_from}")
        
        try:
            with open(self.continue_from, 'r', encoding='utf-8') as f:
                self.existing_conversation_data = json.load(f)
            
            # Validate the conversation data
            if 'conversation' not in self.existing_conversation_data:
                print("❌ Invalid conversation file: missing 'conversation' field")
                return False
            
            existing_turns = len(self.existing_conversation_data['conversation'])
            print(f"✅ Loaded conversation with {existing_turns} existing turns")
            
            # Restore conversation state to message manager
            print("🔄 Restoring conversation state...")
            for turn in self.existing_conversation_data['conversation']:
                character = turn['character']
                message = turn['message']
                self.message_manager.add_turn(character, message)
                self.conversation_log.append(turn)
            
            print(f"✅ Conversation state restored\n")
            return True
            
        except FileNotFoundError:
            print(f"❌ Conversation file not found: {self.continue_from}")
            return False
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON in conversation file")
            return False
        except Exception as e:
            print(f"❌ Error loading conversation: {e}")
            return False
    
    def get_character_response(self, character: str) -> str:
        """
        Get a response from the specified character.
        
        Args:
            character: 'a' or 'b'
            
        Returns:
            The character's response, or empty string if failed
        """
        # Get properly formatted messages for this character
        messages = self.message_manager.get_messages_for_character(character)
        
        # Get response from LLM
        response = self.llm_client.chat_completion(messages)
        
        return response if response else ""
    
    def initialize_conversation_file(self):
        """Initialize the conversation file with metadata."""
        conv_config = self.config_loader.config['conversation_config']
        
        if not conv_config.get('save_conversation', True):
            return
        
        # Create output directory
        output_dir = Path(conv_config.get('output_dir', 'conversations'))
        output_dir.mkdir(exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        scenario_name = self.config_loader.config['scenario_name'].replace(' ', '_')
        
        # If continuing, add suffix to filename
        if self.continue_from:
            filename = f"{scenario_name}_continued_{timestamp}.json"
        else:
            filename = f"{scenario_name}_{timestamp}.json"
        
        self.conversation_filepath = output_dir / filename
        
        # Initialize file with metadata
        if self.continue_from and self.existing_conversation_data:
            # Clone existing conversation data
            conversation_data = {
                'scenario': self.existing_conversation_data['scenario'],
                'original_timestamp': self.existing_conversation_data['timestamp'],
                'continued_timestamp': timestamp,
                'characters': self.existing_conversation_data['characters'].copy(),
                'conversation': self.existing_conversation_data['conversation'].copy(),
                'continued_from': str(self.continue_from)
            }
            print(f"📋 Cloning {len(conversation_data['conversation'])} existing turns to new file")
        else:
            conversation_data = {
                'scenario': self.config_loader.config['scenario_name'],
                'timestamp': timestamp,
                'characters': {
                    'a': self.config_loader.config['character_a_name'],
                    'b': self.config_loader.config['character_b_name']
                },
                'conversation': []
            }
        
        with open(self.conversation_filepath, 'w', encoding='utf-8') as f:
            json.dump(conversation_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Conversation will be saved to: {self.conversation_filepath}\n")
    
    def append_turn_to_file(self, turn_data: dict):
        """Append a turn to the conversation file."""
        if not self.conversation_filepath:
            return
        
        # Read current data
        with open(self.conversation_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Append new turn
        data['conversation'].append(turn_data)
        
        # Write back
        with open(self.conversation_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def wait_for_space_interrupt(self) -> bool:
        """
        Wait for SPACE keypress with timeout.
        
        Returns:
            True if SPACE was pressed, False if timeout
        """
        print(f"⏸️  Press SPACE to interrupt ({self.timeout}s timeout)...", end='', flush=True)
        
        # Save terminal settings
        old_settings = termios.tcgetattr(sys.stdin)
        
        try:
            # Set terminal to raw mode
            tty.setraw(sys.stdin.fileno())
            
            # Wait for input with timeout
            ready, _, _ = select.select([sys.stdin], [], [], self.timeout)
            
            if ready:
                char = sys.stdin.read(1)
                print("\r" + " " * 80 + "\r", end='')  # Clear the line
                
                if char == ' ':
                    return True
            else:
                # Timeout
                print("\r" + " " * 80 + "\r", end='')  # Clear the line
            
            return False
        
        finally:
            # Restore terminal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    
    def get_user_message(self, character: str) -> tuple:
        """
        Prompt user for a manual message.
        
        Args:
            character: 'a' or 'b' for which character
        
        Returns:
            Tuple of (message, should_resume_auto)
        """
        char_name = (self.config_loader.config['character_a_name'] 
                     if character == 'a' 
                     else self.config_loader.config['character_b_name'])
        
        print(f"\n🎮 [INTERACTIVE MODE ACTIVATED]")
        print(f"\nEnter message for {char_name} (or type 'auto' to resume automatic mode):")
        print("> ", end='', flush=True)
        
        message = input().strip()
        
        if message.lower() == 'auto':
            print("\n✅ Resuming automatic mode\n")
            return None, True
        
        return message, False
    
    def run_conversation(self, additional_turns: int = None) -> bool:
        """
        Run the main conversation loop.
        
        Args:
            additional_turns: If continuing, number of additional turns to add
        
        Returns:
            True if successful, False if error occurred
        """
        config = self.config_loader.config
        conv_config = config['conversation_config']
        
        # Initialize conversation file
        self.initialize_conversation_file()
        
        # Determine starting character and turn numbers
        char_a_name = config['character_a_name']
        char_b_name = config['character_b_name']
        
        if self.continue_from and self.existing_conversation_data:
            # Continuing existing conversation
            existing_turns = len(self.existing_conversation_data['conversation'])
            max_turns = additional_turns if additional_turns else conv_config['max_turns']
            start_turn = existing_turns + 1
            
            # Determine next speaker based on last turn
            last_turn = self.existing_conversation_data['conversation'][-1]
            last_speaker = last_turn['character']
            current_char = 'b' if last_speaker == 'a' else 'a'
            
            print(f"🔄 Continuing Conversation...")
            print("="*60)
            print(f"📊 Existing turns: {existing_turns}")
            print(f"➕ Adding: {max_turns} more turns")
            print(f"👤 Next speaker: {char_a_name if current_char == 'a' else char_b_name}")
            print("="*60)
            
            # No initial message when continuing
            initial_msg = ''
        else:
            # New conversation
            current_char = config['starting_character']
            start_turn = 1
            max_turns = conv_config['max_turns']
            
            print("🎭 Starting Conversation...")
            print("="*60)
            
            # Initial message (optional)
            initial_msg = conv_config.get('initial_message', '')
            
        if initial_msg:
            print(f"\n💬 {char_a_name if current_char == 'a' else char_b_name}: {initial_msg}")
            self.message_manager.add_turn(current_char, initial_msg)
            
            # Log and save initial message
            turn_data = {
                'turn': 0,
                'character': current_char,
                'name': char_a_name if current_char == 'a' else char_b_name,
                'message': initial_msg
            }
            self.conversation_log.append(turn_data)
            self.append_turn_to_file(turn_data)
            
            # Switch to other character for first response
            current_char = 'b' if current_char == 'a' else 'a'
        
        # Main conversation loop
        end_turn = start_turn + max_turns - 1
        
        for turn in range(start_turn, end_turn + 1):
            char_name = char_a_name if current_char == 'a' else char_b_name
            
            # Show mode indicator
            mode_indicator = "🤖 [AUTO MODE]" if self.auto_mode else "🎮 [INTERACTIVE MODE]"
            print(f"\n{mode_indicator}")
            print(f"[Turn {turn}/{end_turn}] Character: {char_name}")
            
            user_provided = False
            response = None
            
            # Check for interrupt in auto mode
            if self.auto_mode:
                if self.wait_for_space_interrupt():
                    # User pressed SPACE - switch to interactive
                    message, resume_auto = self.get_user_message(current_char)
                    
                    if resume_auto:
                        # User typed 'auto' - resume automatic mode
                        self.auto_mode = True
                        response = self.get_character_response(current_char)
                    else:
                        # User provided message
                        response = message
                        user_provided = True
                        print(f"\n✅ Manual message added for {char_name}\n")
                else:
                    # Timeout - continue with automatic
                    response = self.get_character_response(current_char)
            else:
                # Already in interactive mode - always prompt
                message, resume_auto = self.get_user_message(current_char)
                
                if resume_auto:
                    # User wants to resume auto
                    self.auto_mode = True
                    response = self.get_character_response(current_char)
                else:
                    # User provided message
                    response = message
                    user_provided = True
                    print(f"\n✅ Manual message added for {char_name}\n")
            
            if not response:
                print(f"❌ Failed to get response from {char_name}")
                return False
            
            # Add to conversation
            self.message_manager.add_turn(current_char, response)
            
            # Log, save, and display
            turn_data = {
                'turn': turn,
                'character': current_char,
                'name': char_name,
                'message': response,
                'user_provided': user_provided
            }
            self.conversation_log.append(turn_data)
            self.append_turn_to_file(turn_data)  # Save after each turn!
            
            print(f"💬 {char_name}: {response}")
            
            # Switch to other character
            current_char = 'b' if current_char == 'a' else 'a'
        
        print("\n" + "="*60)
        print("✅ Conversation complete!")
        if self.conversation_filepath:
            print(f"💾 Final conversation saved to: {self.conversation_filepath}")
        print("="*60)
        
        return True
    
    def run(self, additional_turns: int = None):
        """
        Main entry point to run the application.
        
        Args:
            additional_turns: If continuing, number of additional turns to add
        """
        try:
            # Initialize
            if not self.initialize():
                print("❌ Initialization failed")
                return
            
            # Load existing conversation if continuing
            if self.continue_from:
                if not self.load_existing_conversation():
                    print("❌ Failed to load existing conversation")
                    return
            
            # Run conversation (saves incrementally)
            if not self.run_conversation(additional_turns):
                print("❌ Conversation failed")
                return
            
            print("\n✨ All done!\n")
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Conversation interrupted by user")
            if self.conversation_filepath:
                print(f"💾 Conversation saved up to this point: {self.conversation_filepath}")
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()


def main():
    """Main entry point."""
    import argparse
    
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Dual Agent Chat - Two AI agents in conversation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start a new conversation
  python main.py
  python main.py my_config.json
  
  # Continue an existing conversation
  python main.py --continue conversations/my_chat.json --add-turns 5
  python main.py my_config.json --continue conversations/my_chat.json --add-turns 10
  
  # Start in interactive mode
  python main.py --interactive
  
  # Custom interrupt timeout
  python main.py --interrupt-timeout 10
        """
    )
    
    parser.add_argument(
        'config',
        nargs='?',
        default='app.json',
        help='Path to configuration JSON file (default: app.json)'
    )
    
    parser.add_argument(
        '--continue',
        dest='continue_from',
        metavar='CONVERSATION_FILE',
        help='Path to existing conversation JSON to continue from'
    )
    
    parser.add_argument(
        '--add-turns',
        dest='add_turns',
        type=int,
        metavar='N',
        help='Number of additional turns to add when continuing (required with --continue)'
    )
    
    parser.add_argument(
        '--interrupt-timeout',
        dest='interrupt_timeout',
        type=int,
        metavar='SECONDS',
        help='Timeout in seconds for SPACE interrupt (default: 5 or from config)'
    )
    
    parser.add_argument(
        '--interactive',
        dest='interactive_mode',
        action='store_true',
        help='Start in interactive mode (manually enter all messages)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.continue_from and not args.add_turns:
        parser.error("--add-turns is required when using --continue")
    
    if args.add_turns and not args.continue_from:
        parser.error("--add-turns can only be used with --continue")
    
    # Display what we're doing
    if args.continue_from:
        print(f"📋 Configuration: {args.config}")
        print(f"🔄 Continuing from: {args.continue_from}")
        print(f"➕ Adding {args.add_turns} turns\n")
    else:
        if args.config != "app.json":
            print(f"📋 Using configuration: {args.config}\n")
    
    if args.interactive_mode:
        print("🎮 Starting in INTERACTIVE mode\n")
    
    # Create and run app
    app = DualAgentChat(
        args.config, 
        continue_from=args.continue_from, 
        interrupt_timeout=args.interrupt_timeout,
        interactive_mode=args.interactive_mode
    )
    app.run(additional_turns=args.add_turns)


if __name__ == "__main__":
    main()
