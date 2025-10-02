"""
Message manager for dual agent chat system.
Handles the single message list with role and system prompt switching.
"""

from typing import List, Dict, Any
from copy import deepcopy


class MessageManager:
    """
    Manages the conversation message list with role switching.
    
    Key concept: Instead of maintaining two separate message lists,
    we maintain ONE list and switch roles + system prompt for each turn.
    """
    
    def __init__(self, world_info: str, char_a_info: str, char_b_info: str,
                 char_a_name: str, char_b_name: str):
        """
        Initialize the message manager.
        
        Args:
            world_info: World/setting description
            char_a_info: Character A's card/description
            char_b_info: Character B's card/description
            char_a_name: Character A's name
            char_b_name: Character B's name
        """
        self.world_info = world_info
        self.char_a_info = char_a_info
        self.char_b_info = char_b_info
        self.char_a_name = char_a_name
        self.char_b_name = char_b_name
        
        # The single message list (without system prompt)
        self.messages: List[Dict[str, str]] = []
        
        # Track whose turn it is ('a' or 'b')
        self.current_speaker = None
    
    def build_system_prompt(self, character: str) -> str:
        """
        Build system prompt for the given character.
        System prompt = World Info + Character Info
        
        Args:
            character: 'a' or 'b'
            
        Returns:
            Complete system prompt
        """
        char_info = self.char_a_info if character == 'a' else self.char_b_info
        char_name = self.char_a_name if character == 'a' else self.char_b_name
        
        system_prompt = f"""{self.world_info}

---

{char_info}

---

You are {char_name}. Stay in character and respond naturally to the conversation."""
        
        return system_prompt
    
    def add_message(self, role: str, content: str):
        """
        Add a message to the conversation history.
        
        Args:
            role: 'user' or 'assistant'
            content: Message content
        """
        self.messages.append({
            "role": role,
            "content": content
        })
    
    def switch_roles(self) -> List[Dict[str, str]]:
        """
        Switch all user ↔ assistant roles in the message list.
        This is called when switching speakers.
        
        Returns:
            New message list with roles switched
        """
        switched_messages = []
        for msg in self.messages:
            new_role = "assistant" if msg["role"] == "user" else "user"
            switched_messages.append({
                "role": new_role,
                "content": msg["content"]
            })
        return switched_messages
    
    def get_messages_for_character(self, character: str) -> List[Dict[str, str]]:
        """
        Get the complete message list formatted for the given character.
        This includes the system prompt and properly oriented roles.
        
        Args:
            character: 'a' or 'b'
            
        Returns:
            Complete message list ready for LLM API
        """
        # Build system prompt for this character
        system_prompt = self.build_system_prompt(character)
        
        # Determine if we need to switch roles
        # If current speaker matches the character, use messages as-is
        # If different, switch the roles
        if character == self.current_speaker or self.current_speaker is None:
            # Use messages as they are
            conversation_messages = deepcopy(self.messages)
        else:
            # Switch roles because we're changing speakers
            conversation_messages = self.switch_roles()
        
        # Prepend system message
        full_messages = [
            {"role": "system", "content": system_prompt}
        ] + conversation_messages
        
        return full_messages
    
    def add_turn(self, character: str, message: str):
        """
        Add a character's turn to the conversation.
        
        This handles the role orientation automatically:
        - If this is the first message, add as 'assistant' (character speaks first)
        - If continuing, add as 'assistant' (the speaker always responds as assistant)
        - The previous speaker's messages become 'user' messages from current speaker's POV
        
        Args:
            character: 'a' or 'b'
            message: The message content
        """
        if self.current_speaker is None:
            # First message - this character is starting
            self.current_speaker = character
            self.add_message("assistant", message)
        elif self.current_speaker == character:
            # Same speaker continuing (shouldn't normally happen in alternating chat)
            self.add_message("assistant", message)
        else:
            # Different speaker - switch perspective
            # From the new speaker's POV, the previous message was from 'user'
            # So we switch roles, then add new message as 'assistant'
            self.messages = self.switch_roles()
            self.current_speaker = character
            self.add_message("assistant", message)
    
    def display_conversation(self):
        """Display the conversation in a readable format."""
        print("\n" + "="*60)
        print("CONVERSATION HISTORY")
        print("="*60)
        
        for i, msg in enumerate(self.messages, 1):
            speaker = self.char_a_name if msg["role"] == "assistant" else self.char_b_name
            if self.current_speaker == 'b':
                # Flip perspective
                speaker = self.char_b_name if msg["role"] == "assistant" else self.char_a_name
            
            print(f"\n[{i}] {speaker}:")
            print(f"    {msg['content']}")
        
        print("\n" + "="*60 + "\n")
    
    def get_message_count(self) -> int:
        """Get the number of messages in the conversation."""
        return len(self.messages)


# Test function
if __name__ == "__main__":
    print("Testing MessageManager...")
    print("="*60)
    
    # Simple test data
    world = "A fantasy tavern setting"
    char_a = "Character A: A friendly merchant"
    char_b = "Character B: A wise herbalist"
    
    manager = MessageManager(world, char_a, char_b, "Eldric", "Mira")
    
    # Simulate conversation
    print("\n1. Eldric starts the conversation:")
    manager.add_turn('a', "Hello! Nice evening, isn't it?")
    msgs = manager.get_messages_for_character('a')
    print(f"   Messages for Eldric: {len(msgs)} messages")
    print(f"   Last message role: {msgs[-1]['role']}")
    
    print("\n2. Mira responds:")
    manager.add_turn('b', "Indeed it is. What brings you here?")
    msgs = manager.get_messages_for_character('b')
    print(f"   Messages for Mira: {len(msgs)} messages")
    print(f"   Last message role: {msgs[-1]['role']}")
    
    print("\n3. Eldric responds:")
    manager.add_turn('a', "I'm a traveling merchant, just passing through.")
    msgs = manager.get_messages_for_character('a')
    print(f"   Messages for Eldric: {len(msgs)} messages")
    
    print("\n4. Display conversation:")
    manager.display_conversation()
    
    print("\n✅ MessageManager test complete!")
