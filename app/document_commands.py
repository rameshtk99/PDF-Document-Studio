"""
Real (non-stub) undo/redo commands for interactive image editing and
footer configuration changes.

app/undo_redo.py's own concrete Command subclasses (MoveImageCommand,
AddImageCommand, etc.) are intentionally left untouched -- their
execute/undo/redo are inert placeholders and test_stage12.py exercises
that exact behavior. These commands build on the same Command /
UndoRedoManager base (app/undo_redo.py) but actually call into
ImageManager / Document, so Ctrl+Z / Ctrl+Y really move, resize, add,
delete, or change properties of objects and footer settings.
"""

from typing import Dict, Optional

from app.undo_redo import Command
from pdf.image_manager import ImageManager, ImagePlacement
from models import Document, FooterConfig, PageConfig


class MoveObjectCommand(Command):
    """Move an image object between two positions.

    `execute()` re-applies the `to` position -- harmless when the move
    already happened live during a canvas drag (the caller pushes this
    command only after the drag ends, purely to record undo history).
    """

    def __init__(self, manager: ImageManager, image_id: str,
                 from_x: float, from_y: float, to_x: float, to_y: float):
        super().__init__()
        self.manager = manager
        self.image_id = image_id
        self.from_x, self.from_y = from_x, from_y
        self.to_x, self.to_y = to_x, to_y
        self.description = (f"Move object ({from_x:.1f},{from_y:.1f}) "
                             f"-> ({to_x:.1f},{to_y:.1f})")

    def execute(self):
        self.manager.set_image_position(self.image_id, self.to_x, self.to_y)

    def undo(self):
        self.manager.set_image_position(self.image_id, self.from_x, self.from_y)

    def redo(self):
        self.execute()


class ResizeObjectCommand(Command):
    """Resize (and, for corner/edge handles that shift the anchor, reposition)
    an image object between two states.

    Several resize handles (TL, T, TR, L, BL) change x/y as well as
    width/height -- tracking position alongside size here (rather than
    splitting into a separate move command) keeps undo/redo a single,
    atomic, always-consistent step regardless of which handle was used.
    """

    def __init__(self, manager: ImageManager, image_id: str,
                 from_x: float, from_y: float, from_width: float, from_height: float,
                 to_x: float, to_y: float, to_width: float, to_height: float):
        super().__init__()
        self.manager = manager
        self.image_id = image_id
        self.from_x, self.from_y = from_x, from_y
        self.from_width, self.from_height = from_width, from_height
        self.to_x, self.to_y = to_x, to_y
        self.to_width, self.to_height = to_width, to_height
        self.description = (f"Resize object {from_width:.0f}x{from_height:.0f} "
                             f"-> {to_width:.0f}x{to_height:.0f}")

    def execute(self):
        self.manager.set_image_position(self.image_id, self.to_x, self.to_y)
        self.manager.set_image_size(self.image_id, self.to_width, self.to_height)

    def undo(self):
        self.manager.set_image_position(self.image_id, self.from_x, self.from_y)
        self.manager.set_image_size(self.image_id, self.from_width, self.from_height)

    def redo(self):
        self.execute()


class ChangeObjectPropertyCommand(Command):
    """Change a single property (opacity, rotation, z_index, ...) of an object."""

    def __init__(self, manager: ImageManager, image_id: str, property_name: str,
                 from_value, to_value):
        super().__init__()
        self.manager = manager
        self.image_id = image_id
        self.property_name = property_name
        self.from_value, self.to_value = from_value, to_value
        self.description = f"Change {property_name}: {from_value} -> {to_value}"

    def execute(self):
        self.manager.set_image_property(self.image_id, self.property_name, self.to_value)

    def undo(self):
        self.manager.set_image_property(self.image_id, self.property_name, self.from_value)

    def redo(self):
        self.execute()


class AddObjectCommand(Command):
    """Add a new image object to a page.

    `image_id` is only known after the first `execute()` mints it via
    `ImageManager.add_image_to_page`. Redo mints a fresh id (the removed
    id from a prior undo cannot be reused) -- fine, since overlay code
    always re-reads the live objects from the document rather than
    caching an id across an undo/redo cycle.
    """

    def __init__(self, manager: ImageManager, page_number: int,
                 placement: ImagePlacement, image_path: Optional[str]):
        super().__init__()
        self.manager = manager
        self.page_number = page_number
        self.placement = placement
        self.image_path = image_path
        self.image_id: Optional[str] = None
        self.description = f"Add image on page {page_number}"

    def execute(self):
        self.image_id = self.manager.add_image_to_page(
            self.page_number, self.placement, self.image_path)

    def undo(self):
        if self.image_id:
            self.manager.remove_image(self.image_id)
            self.image_id = None

    def redo(self):
        self.execute()


class DeleteObjectCommand(Command):
    """Delete an image object, keeping a full snapshot so undo can restore it."""

    def __init__(self, manager: ImageManager, page_number: int, obj):
        super().__init__()
        self.manager = manager
        self.page_number = page_number
        self.image_id = obj.id
        self.placement = ImagePlacement(
            page_number=page_number, x=obj.x, y=obj.y,
            width=obj.width, height=obj.height,
            rotation=obj.rotation, opacity=obj.opacity, z_index=obj.z_index,
        )
        self.image_path = (obj.properties or {}).get('image_path')
        self.description = f"Delete image on page {page_number}"

    def execute(self):
        self.manager.remove_image(self.image_id)

    def undo(self):
        self.image_id = self.manager.add_image_to_page(
            self.page_number, self.placement, self.image_path)

    def redo(self):
        self.execute()


class ChangePageFooterCommand(Command):
    """Apply a new footer config to a single page ("Apply to This Page").

    Undo restores whichever state existed before: either the previous
    page-specific override, or -- if this page had no override yet --
    removes the override entirely so the page falls back to inheriting
    the global footer again (matching Document.get_page_config's own
    fallback behavior).
    """

    def __init__(self, document: Document, page_number: int,
                 before_config: FooterConfig, after_config: FooterConfig,
                 before_had_override: bool):
        super().__init__()
        self.document = document
        self.page_number = page_number
        self.before_config = before_config
        self.after_config = after_config
        self.before_had_override = before_had_override
        self.description = f"Change page {page_number} footer"

    def execute(self):
        page_config = self.document.get_page_config(self.page_number)
        page_config.footer_config = self.after_config
        self.document.set_page_config(self.page_number, page_config)
        self.document.set_modified(True)

    def undo(self):
        if self.before_had_override:
            page_config = self.document.get_page_config(self.page_number)
            page_config.footer_config = self.before_config
            self.document.set_page_config(self.page_number, page_config)
        else:
            self.document.page_configs.pop(self.page_number, None)
        self.document.set_modified(True)

    def redo(self):
        self.execute()


class ResetPageFooterCommand(Command):
    """Remove a page's footer override, falling back to the global footer."""

    def __init__(self, document: Document, page_number: int, before_config: FooterConfig):
        super().__init__()
        self.document = document
        self.page_number = page_number
        self.before_config = before_config
        self.description = f"Reset page {page_number} footer to global"

    def execute(self):
        self.document.page_configs.pop(self.page_number, None)
        self.document.set_modified(True)

    def undo(self):
        page_config = self.document.get_page_config(self.page_number)
        page_config.footer_config = self.before_config
        self.document.set_page_config(self.page_number, page_config)
        self.document.set_modified(True)

    def redo(self):
        self.execute()


class ChangeGlobalFooterCommand(Command):
    """Apply a new global footer config ("Apply to All Pages"), which also
    clears every page-specific override. Undo restores both the previous
    global config and the previous set of per-page overrides.
    """

    def __init__(self, document: Document, before_global: FooterConfig,
                 after_global: FooterConfig, before_page_configs: Dict[int, PageConfig]):
        super().__init__()
        self.document = document
        self.before_global = before_global
        self.after_global = after_global
        self.before_page_configs = before_page_configs
        self.description = "Apply footer to all pages"

    def execute(self):
        self.document.global_settings.footer_config = self.after_global
        self.document.page_configs.clear()
        self.document.set_modified(True)

    def undo(self):
        self.document.global_settings.footer_config = self.before_global
        self.document.page_configs.clear()
        self.document.page_configs.update(self.before_page_configs)
        self.document.set_modified(True)

    def redo(self):
        self.execute()
