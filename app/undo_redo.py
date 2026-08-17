"""
Undo/Redo system for PDF editor

Provides:
- Command-based undo/redo architecture
- History management with configurable limits
- Multiple command types for different operations
- Keyboard shortcut support (Ctrl+Z, Ctrl+Y)
- History branching on new commands after undo
- State queries for UI integration
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


class Command(ABC):
    """Base class for all commands
    
    Attributes:
        timestamp: When command was created
        description: Human-readable description
    """
    
    def __init__(self):
        self.timestamp = datetime.now()
        self.description = ""
    
    @abstractmethod
    def execute(self):
        """Execute the command"""
        pass
    
    @abstractmethod
    def undo(self):
        """Undo the command"""
        pass
    
    @abstractmethod
    def redo(self):
        """Redo the command"""
        pass
    
    def __str__(self) -> str:
        if self.description:
            return self.description
        return self.__class__.__name__


@dataclass
class ImageCommand(Command):
    """Generic image command
    
    Attributes:
        image_id: ID of image being modified
        operation: Type of operation (move, resize, property)
        data: Operation-specific data
    """
    image_id: str = ""
    operation: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        super().__init__()
        if not self.description:
            self.description = f"{self.operation.capitalize()} {self.image_id}"
    
    def __str__(self) -> str:
        """Return string representation"""
        return self.description or f"{self.operation} {self.image_id}"
    
    def execute(self):
        """Execute command (default: do nothing)"""
        pass
    
    def undo(self):
        """Undo command (default: do nothing)"""
        pass
    
    def redo(self):
        """Redo command (default: execute again)"""
        self.execute()


@dataclass
class MoveImageCommand(Command):
    """Move image from one position to another
    
    Attributes:
        image_id: ID of image
        from_x: Original X position
        from_y: Original Y position
        to_x: New X position
        to_y: New Y position
    """
    image_id: str = ""
    from_x: float = 0.0
    from_y: float = 0.0
    to_x: float = 0.0
    to_y: float = 0.0
    
    def __post_init__(self):
        super().__init__()
        if not self.description:
            self.description = f"Move {self.image_id} ({self.from_x:.1f}, {self.from_y:.1f}) → ({self.to_x:.1f}, {self.to_y:.1f})"
    
    def __str__(self) -> str:
        """Return string representation"""
        return self.description
    
    def execute(self):
        """Move to new position"""
        # Actual movement handled by GUI
        pass
    
    def undo(self):
        """Move back to original position"""
        # Swap positions
        self.to_x, self.from_x = self.from_x, self.to_x
        self.to_y, self.from_y = self.from_y, self.to_y
    
    def redo(self):
        """Move to new position again"""
        # Swap positions back
        self.to_x, self.from_x = self.from_x, self.to_x
        self.to_y, self.from_y = self.from_y, self.to_y


@dataclass
class ResizeImageCommand(Command):
    """Resize image from one size to another
    
    Attributes:
        image_id: ID of image
        from_width: Original width
        from_height: Original height
        to_width: New width
        to_height: New height
    """
    image_id: str = ""
    from_width: float = 0.0
    from_height: float = 0.0
    to_width: float = 0.0
    to_height: float = 0.0
    
    def __post_init__(self):
        super().__init__()
        if not self.description:
            self.description = f"Resize {self.image_id} {self.from_width:.1f}×{self.from_height:.1f} → {self.to_width:.1f}×{self.to_height:.1f}"
    
    def __str__(self) -> str:
        """Return string representation"""
        return self.description
    
    def execute(self):
        """Apply new size"""
        pass
    
    def undo(self):
        """Revert to original size"""
        # Swap sizes
        self.to_width, self.from_width = self.from_width, self.to_width
        self.to_height, self.from_height = self.from_height, self.to_height
    
    def redo(self):
        """Apply new size again"""
        # Swap sizes back
        self.to_width, self.from_width = self.from_width, self.to_width
        self.to_height, self.from_height = self.from_height, self.to_height


@dataclass
class ChangePropertyCommand(Command):
    """Change image property (opacity, rotation, z-index, etc.)
    
    Attributes:
        image_id: ID of image
        property_name: Name of property
        from_value: Original value
        to_value: New value
    """
    image_id: str = ""
    property_name: str = ""
    from_value: Any = None
    to_value: Any = None
    
    def __post_init__(self):
        super().__init__()
        if not self.description:
            self.description = f"Change {self.image_id}.{self.property_name} {self.from_value} → {self.to_value}"
    
    def __str__(self) -> str:
        """Return string representation"""
        return self.description
    
    def execute(self):
        """Apply new value"""
        pass
    
    def undo(self):
        """Revert to original value"""
        # Swap values
        self.to_value, self.from_value = self.from_value, self.to_value
    
    def redo(self):
        """Apply new value again"""
        # Swap values back
        self.to_value, self.from_value = self.from_value, self.to_value


@dataclass
class AddImageCommand(Command):
    """Add new image to page
    
    Attributes:
        image_id: ID of new image
        image_data: Image configuration (position, size, properties)
    """
    image_id: str = ""
    image_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        super().__init__()
        if not self.description:
            self.description = f"Add image {self.image_id}"
    
    def __str__(self) -> str:
        """Return string representation"""
        return self.description
    
    def execute(self):
        """Add image"""
        pass
    
    def undo(self):
        """Remove image"""
        pass
    
    def redo(self):
        """Add image again"""
        self.execute()


@dataclass
class DeleteImageCommand(Command):
    """Delete image from page
    
    Attributes:
        image_id: ID of image to delete
        image_data: Saved image configuration for undo
    """
    image_id: str = ""
    image_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        super().__init__()
        if not self.description:
            self.description = f"Delete image {self.image_id}"
    
    def __str__(self) -> str:
        """Return string representation"""
        return self.description
    
    def execute(self):
        """Delete image"""
        pass
    
    def undo(self):
        """Restore image"""
        pass
    
    def redo(self):
        """Delete image again"""
        self.execute()


class UndoRedoManager:
    """Manages undo/redo history
    
    Features:
    - Command recording and execution
    - Undo/redo navigation
    - History branching on new commands after undo
    - Configurable history size limit
    - State queries for UI integration
    """
    
    def __init__(self, max_history: int = 100):
        """
        Initialize undo/redo manager
        
        Args:
            max_history: Maximum number of commands to keep
        """
        self.history: List[Command] = []
        self.current_position: int = -1  # -1 = before first command
        self.max_history: int = max_history
    
    def execute(self, command: Command):
        """
        Execute a command and record it in history
        
        Args:
            command: Command to execute
        """
        # Execute the command
        command.execute()
        
        # If we're not at the end of history, truncate (branching)
        if self.current_position < len(self.history) - 1:
            self.history = self.history[:self.current_position + 1]
        
        # Add command to history
        self.history.append(command)
        self.current_position += 1
        
        # Enforce maximum history size
        if len(self.history) > self.max_history:
            self.history.pop(0)
            self.current_position -= 1
    
    def undo(self) -> Optional[Command]:
        """
        Undo the last command
        
        Returns:
            The command that was undone, or None if at beginning
        """
        if not self.can_undo():
            return None
        
        command = self.history[self.current_position]
        command.undo()
        self.current_position -= 1
        
        return command
    
    def redo(self) -> Optional[Command]:
        """
        Redo the next command
        
        Returns:
            The command that was redone, or None if at end
        """
        if not self.can_redo():
            return None
        
        self.current_position += 1
        command = self.history[self.current_position]
        command.redo()
        
        return command
    
    def can_undo(self) -> bool:
        """
        Check if undo is available
        
        Returns:
            True if can undo
        """
        return self.current_position >= 0
    
    def can_redo(self) -> bool:
        """
        Check if redo is available
        
        Returns:
            True if can redo
        """
        return self.current_position < len(self.history) - 1
    
    def clear(self):
        """Clear all history"""
        self.history.clear()
        self.current_position = -1
    
    def get_history_info(self) -> Dict[str, Any]:
        """
        Get current history state information
        
        Returns:
            Dict with history statistics
        """
        return {
            'total_commands': len(self.history),
            'current_position': self.current_position,
            'can_undo': self.can_undo(),
            'can_redo': self.can_redo(),
            'undo_command': str(self.history[self.current_position]) if self.can_undo() else None,
            'redo_command': str(self.history[self.current_position + 1]) if self.can_redo() else None,
        }
    
    def get_history_snapshot(self) -> List[Dict[str, Any]]:
        """
        Get snapshot of entire history
        
        Returns:
            List of command descriptions
        """
        snapshot = []
        for idx, cmd in enumerate(self.history):
            snapshot.append({
                'index': idx,
                'description': str(cmd),
                'timestamp': cmd.timestamp.isoformat(),
                'is_current': idx == self.current_position,
                'is_undone': idx > self.current_position,
            })
        return snapshot
    
    def undo_to(self, position: int) -> Optional[List[Command]]:
        """
        Undo multiple commands to reach specific position
        
        Args:
            position: Target position in history
            
        Returns:
            List of commands that were undone, or None if invalid
        """
        if position < -1 or position >= len(self.history):
            return None
        
        undone = []
        while self.current_position > position:
            cmd = self.undo()
            if cmd:
                undone.append(cmd)
        
        return undone
    
    def redo_to(self, position: int) -> Optional[List[Command]]:
        """
        Redo multiple commands to reach specific position
        
        Args:
            position: Target position in history
            
        Returns:
            List of commands that were redone, or None if invalid
        """
        if position < 0 or position >= len(self.history):
            return None
        
        redone = []
        while self.current_position < position:
            cmd = self.redo()
            if cmd:
                redone.append(cmd)
        
        return redone
    
    def get_undo_stack(self) -> List[str]:
        """
        Get list of commands available to undo
        
        Returns:
            List of command descriptions
        """
        if self.current_position < 0:
            return []
        return [str(self.history[i]) for i in range(self.current_position + 1)]
    
    def get_redo_stack(self) -> List[str]:
        """
        Get list of commands available to redo
        
        Returns:
            List of command descriptions
        """
        if self.current_position >= len(self.history) - 1:
            return []
        return [str(self.history[i]) for i in range(self.current_position + 1, len(self.history))]
