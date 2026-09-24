using Avalonia;
using Avalonia.Headless;
using PDFDocumentStudio.Tests.App;

[assembly: AvaloniaTestApplication(typeof(TestAppBuilder))]

namespace PDFDocumentStudio.Tests.App;

public static class TestAppBuilder
{
    public static AppBuilder BuildAvaloniaApp() =>
        AppBuilder.Configure<PDFDocumentStudio.App.App>()
            .UseSkia()
            // UseHeadlessDrawing=false actually renders via Skia instead of a no-op recorder, so
            // CaptureRenderedFrame() (used to catch "data is correct but nothing ever repainted"
            // bugs — see CanvasRepaintTests) returns real pixels.
            .UseHeadless(new AvaloniaHeadlessPlatformOptions { UseHeadlessDrawing = false });
}
