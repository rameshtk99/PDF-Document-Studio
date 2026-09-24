# PDF Document Studio

Cross-platform desktop PDF editor (Windows/Linux/macOS) built on .NET 10 and Avalonia UI. A ground-up rewrite of the legacy Python/Tkinter application preserved at `backup_2026-09-24/` for reference — see `docs/LEGACY_FEATURE_INVENTORY.md` for the full feature audit this rewrite is built from.

## What it does

Opens PDFs, lets you place page-anchored footers (with content-aware placement — the footer never blindly overlaps text), add text/image objects, and export or compress the result. See `docs/FEATURES.md` for the full status of every feature relative to the legacy app.

## Project layout

```
src/
  PDFDocumentStudio.Core        domain model, commands/undo-redo, text layout, footer math, serialization
  PDFDocumentStudio.Pdf         PDF loading/rendering/export/compression (PDFsharp + PDFium)
  PDFDocumentStudio.Rendering   page bitmap cache, continuous-scroll layout planner
  PDFDocumentStudio.Features    editor session, footer preview, open/save/export orchestration
  PDFDocumentStudio.App         Avalonia UI
tests/
  PDFDocumentStudio.Tests       xUnit v3 — Core/Pdf unit+integration tests, Avalonia.Headless UI tests
docs/
  LEGACY_FEATURE_INVENTORY.md   the legacy app's behavior, audited from source — the spec this rewrite follows
  ARCHITECTURE.md, FEATURES.md, BUILD.md, TESTING.md, PERFORMANCE.md, MIGRATION.md
backup_2026-09-24/              the original Python app, preserved unmodified as reference
```

## Build & run

Requires the .NET 10 SDK.

```
dotnet build PDFDocumentStudio.slnx
dotnet run --project src/PDFDocumentStudio.App
```

## Test

```
dotnet run --project tests/PDFDocumentStudio.Tests
```

(`dotnet test` doesn't yet work with .NET 10's Microsoft.Testing.Platform-based xUnit v3 runner in this SDK — see `docs/BUILD.md`.)

See `docs/ARCHITECTURE.md`, `docs/FEATURES.md`, `docs/BUILD.md`, `docs/TESTING.md`, `docs/PERFORMANCE.md`, `docs/MIGRATION.md` for more.
