#!/usr/bin/env python3
"""
Test Suite for Stage 12: Undo/Redo System

Tests command-based undo/redo functionality:
- Command recording and execution
- Undo/redo navigation
- History tracking
- Multiple command types
- History limits and management
- Keyboard shortcuts
- History state queries
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from pdf.pdf_loader import PDFLoader
from pdf.image_manager import ImageManager, ImagePlacement
from app.undo_redo import (
    UndoRedoManager, Command, ImageCommand, 
    MoveImageCommand, ResizeImageCommand, ChangePropertyCommand,
    DeleteImageCommand, AddImageCommand
)
from models.models import Document


def test_command_recording():
    """Test basic command recording"""
    print("Test 1: Command Recording")
    print("-" * 50)
    
    try:
        manager = UndoRedoManager()
        
        # Create and execute a command
        cmd = ImageCommand("test_image", "move", {"x": 100.0, "y": 100.0})
        manager.execute(cmd)
        
        assert len(manager.history) == 1, "Command not recorded"
        print(f"✓ Command recorded: {cmd}")
        
        # History position should be at end
        assert manager.current_position == 0, "Position not tracking"
        print(f"✓ History position: {manager.current_position}")
        
        # Execute another command
        cmd2 = ImageCommand("test_image2", "resize", {"width": 200.0, "height": 150.0})
        manager.execute(cmd2)
        
        assert len(manager.history) == 2, "Second command not recorded"
        print(f"✓ Second command recorded")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_undo_functionality():
    """Test undo operation"""
    print("Test 2: Undo Functionality")
    print("-" * 50)
    
    try:
        manager = UndoRedoManager()
        
        # Execute 3 commands
        for i in range(3):
            cmd = ImageCommand(f"image_{i}", "move", {"x": 100.0 * (i+1), "y": 100.0})
            manager.execute(cmd)
        
        assert len(manager.history) == 3, "Not all commands recorded"
        print(f"✓ Executed 3 commands")
        
        # Undo one
        undone = manager.undo()
        assert undone is not None, "Undo returned None"
        assert len(manager.history) == 3, "Command removed from history"
        print(f"✓ Undo 1: {undone.image_id}")
        
        # Undo second
        undone = manager.undo()
        assert undone is not None, "Second undo failed"
        print(f"✓ Undo 2: {undone.image_id}")
        
        # Undo third
        undone = manager.undo()
        assert undone is not None, "Third undo failed"
        print(f"✓ Undo 3: {undone.image_id}")
        
        # Cannot undo more
        undone = manager.undo()
        assert undone is None, "Should not undo past beginning"
        print(f"✓ Cannot undo past beginning")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_redo_functionality():
    """Test redo operation"""
    print("Test 3: Redo Functionality")
    print("-" * 50)
    
    try:
        manager = UndoRedoManager()
        
        # Execute 3 commands
        for i in range(3):
            cmd = ImageCommand(f"image_{i}", "move", {"x": 100.0 * (i+1), "y": 100.0})
            manager.execute(cmd)
        
        print(f"✓ Executed 3 commands")
        
        # Undo 2
        manager.undo()
        manager.undo()
        print(f"✓ Undid 2 commands")
        
        # Redo one
        redone = manager.redo()
        assert redone is not None, "Redo returned None"
        print(f"✓ Redo 1: {redone.image_id}")
        
        # Redo second
        redone = manager.redo()
        assert redone is not None, "Second redo failed"
        print(f"✓ Redo 2: {redone.image_id}")
        
        # Cannot redo more
        redone = manager.redo()
        assert redone is None, "Should not redo past end"
        print(f"✓ Cannot redo past end")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_history_branching():
    """Test history branching when executing after undo"""
    print("Test 4: History Branching")
    print("-" * 50)
    
    try:
        manager = UndoRedoManager()
        
        # Execute 3 commands
        for i in range(3):
            cmd = ImageCommand(f"image_{i}", "move", {"x": 100.0 * (i+1), "y": 100.0})
            manager.execute(cmd)
        
        print(f"✓ Executed 3 commands")
        
        # Undo 2
        manager.undo()
        manager.undo()
        print(f"✓ Undid 2 commands")
        
        # Execute new command (should branch history)
        cmd_new = ImageCommand("image_new", "resize", {"width": 300.0, "height": 250.0})
        manager.execute(cmd_new)
        
        # History should have only 2 original + 1 new = 3 total
        assert len(manager.history) == 2, "History not branched correctly"
        print(f"✓ History branched: {len(manager.history)} commands in history")
        
        # Redo should not be possible
        redone = manager.redo()
        assert redone is None, "Redo available after branch"
        print(f"✓ Redo cleared after branch")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_command_types():
    """Test different command types"""
    print("Test 5: Different Command Types")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    try:
        doc = PDFLoader.load_pdf(str(pdf_files[0]))
        manager = ImageManager()
        manager.load_document(doc)
        
        # Create undo/redo manager
        undo_mgr = UndoRedoManager()
        
        # Test MoveImageCommand
        move_cmd = MoveImageCommand("image1", 50.0, 50.0, 100.0, 100.0)
        undo_mgr.execute(move_cmd)
        print(f"✓ MoveImageCommand: {move_cmd}")
        
        # Test ResizeImageCommand
        resize_cmd = ResizeImageCommand("image1", 200.0, 150.0, 250.0, 200.0)
        undo_mgr.execute(resize_cmd)
        print(f"✓ ResizeImageCommand: {resize_cmd}")
        
        # Test ChangePropertyCommand
        prop_cmd = ChangePropertyCommand("image1", "opacity", 100.0, 75.0)
        undo_mgr.execute(prop_cmd)
        print(f"✓ ChangePropertyCommand: opacity 100→75")
        
        # Test AddImageCommand
        add_cmd = AddImageCommand("image_new", {"x": 50, "y": 50, "width": 100, "height": 100})
        undo_mgr.execute(add_cmd)
        print(f"✓ AddImageCommand: new image added")
        
        # Test DeleteImageCommand
        delete_cmd = DeleteImageCommand("image_new", {"x": 50, "y": 50, "width": 100, "height": 100})
        undo_mgr.execute(delete_cmd)
        print(f"✓ DeleteImageCommand: image deleted")
        
        assert len(undo_mgr.history) == 5, "Not all commands recorded"
        print(f"✓ All 5 commands recorded in history")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_history_limits():
    """Test history size limits"""
    print("Test 6: History Size Limits")
    print("-" * 50)
    
    try:
        manager = UndoRedoManager(max_history=10)
        
        # Execute 15 commands (should keep only last 10)
        for i in range(15):
            cmd = ImageCommand(f"image_{i}", "move", {"x": float(i), "y": float(i)})
            manager.execute(cmd)
        
        # History should be capped at 10
        assert len(manager.history) == 10, "History not limited to max_history"
        print(f"✓ History capped at {len(manager.history)} (max 10)")
        
        # First command should be image_5 (commands 0-4 removed)
        first_cmd = manager.history[0]
        assert first_cmd.image_id == "image_5", "Old commands not removed"
        print(f"✓ Old commands removed: first is {first_cmd.image_id}")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_history_queries():
    """Test history state queries"""
    print("Test 7: History State Queries")
    print("-" * 50)
    
    try:
        manager = UndoRedoManager()
        
        # Initially, cannot undo or redo
        assert not manager.can_undo(), "Should not be able to undo initially"
        assert not manager.can_redo(), "Should not be able to redo initially"
        print(f"✓ Initial state: no undo/redo available")
        
        # Execute a command
        cmd = ImageCommand("image_1", "move", {"x": 100.0, "y": 100.0})
        manager.execute(cmd)
        
        assert manager.can_undo(), "Should be able to undo after command"
        assert not manager.can_redo(), "Should not be able to redo after new command"
        print(f"✓ After execute: can undo, cannot redo")
        
        # Undo
        manager.undo()
        
        assert not manager.can_undo(), "Should not be able to undo at beginning"
        assert manager.can_redo(), "Should be able to redo after undo"
        print(f"✓ After undo: cannot undo, can redo")
        
        # Get history info
        info = manager.get_history_info()
        assert 'total_commands' in info, "Missing total_commands"
        assert 'current_position' in info, "Missing current_position"
        assert 'can_undo' in info, "Missing can_undo"
        assert 'can_redo' in info, "Missing can_redo"
        print(f"✓ History info: {info}")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_clear_history():
    """Test clearing history"""
    print("Test 8: Clear History")
    print("-" * 50)
    
    try:
        manager = UndoRedoManager()
        
        # Execute 5 commands
        for i in range(5):
            cmd = ImageCommand(f"image_{i}", "move", {"x": float(i), "y": float(i)})
            manager.execute(cmd)
        
        assert len(manager.history) == 5, "Commands not recorded"
        print(f"✓ Recorded 5 commands")
        
        # Clear history
        manager.clear()
        
        assert len(manager.history) == 0, "History not cleared"
        assert manager.current_position == -1, "Position not reset"
        assert not manager.can_undo(), "Can undo after clear"
        assert not manager.can_redo(), "Can redo after clear"
        print(f"✓ History cleared completely")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_keyboard_shortcuts():
    """Test keyboard shortcut simulation"""
    print("Test 9: Keyboard Shortcuts Simulation")
    print("-" * 50)
    
    try:
        manager = UndoRedoManager()
        
        # Record some commands
        for i in range(3):
            cmd = ImageCommand(f"image_{i}", "move", {"x": float(i)*100, "y": float(i)*100})
            manager.execute(cmd)
        
        print(f"✓ Executed 3 commands")
        
        # Simulate Ctrl+Z (undo)
        undone = manager.undo()
        assert undone is not None, "Ctrl+Z should undo"
        print(f"✓ Ctrl+Z (undo): {undone.image_id}")
        
        # Simulate Ctrl+Z again
        undone = manager.undo()
        assert undone is not None, "Second Ctrl+Z should undo"
        print(f"✓ Ctrl+Z (undo): {undone.image_id}")
        
        # Simulate Ctrl+Y (redo)
        redone = manager.redo()
        assert redone is not None, "Ctrl+Y should redo"
        print(f"✓ Ctrl+Y (redo): {redone.image_id}")
        
        # Simulate Ctrl+Z to undo what Ctrl+Y did
        undone = manager.undo()
        assert undone is not None, "Ctrl+Z should undo after redo"
        print(f"✓ Ctrl+Z after Ctrl+Y: {undone.image_id}")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 50)
    print("STAGE 12 TEST SUITE: Undo/Redo System")
    print("=" * 50 + "\n")
    
    tests = [
        test_command_recording,
        test_undo_functionality,
        test_redo_functionality,
        test_history_branching,
        test_command_types,
        test_history_limits,
        test_history_queries,
        test_clear_history,
        test_keyboard_shortcuts,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test crashed: {e}\n")
            results.append(False)
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("=" * 50)
    
    if all(results):
        print("\n✅ All tests PASSED - Undo/redo system ready")
        return True
    else:
        print("\n⚠ Some tests failed - Review and fix")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
