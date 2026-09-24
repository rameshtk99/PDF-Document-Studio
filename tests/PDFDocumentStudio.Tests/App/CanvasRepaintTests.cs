using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Media.Imaging;
using Avalonia.Threading;
using PDFDocumentStudio.App;
using SkiaSharp;

namespace PDFDocumentStudio.Tests.App;

/// <summary>
/// Regression test for a real bug found via manual testing: the page canvas is a custom Control
/// that reads Page.Bitmap/FooterOverlay directly inside Render() rather than through a bound
/// Avalonia property, so when a background render completes (or a footer gets applied) and
/// mutates that data in place, nothing ever told Avalonia to repaint — the underlying data was
/// correct (which asserting on the view model alone would show as "passing"), but the screen
/// stayed blank forever. This test captures actual rendered pixels, not just view-model state.
/// </summary>
public class CanvasRepaintTests
{
    private static string SamplePdfPath => Path.Combine(AppContext.BaseDirectory, "Assets", "sample.pdf");

    [AvaloniaFact]
    public async Task PageCanvas_RepaintsWithNonWhitePixels_AfterBackgroundBitmapArrives()
    {
        var window = new MainWindow();
        window.Show();
        var vm = (PDFDocumentStudio.App.ViewModels.MainViewModel)window.DataContext!;
        vm.LoadPdf(SamplePdfPath);
        Dispatcher.UIThread.RunJobs();
        window.UpdateLayout();

        for (var i = 0; i < 60 && vm.Pages[0].Bitmap is null; i++)
        {
            await Task.Delay(100);
            Dispatcher.UIThread.RunJobs();
        }
        Assert.NotNull(vm.Pages[0].Bitmap);

        window.UpdateLayout();
        using var frame = window.CaptureRenderedFrame();
        Assert.NotNull(frame);
        Assert.True(ContainsNonWhitePixel(frame!), "Expected the canvas to actually paint page content, not stay visually blank.");

        window.Close();
    }

    private static bool ContainsNonWhitePixel(WriteableBitmap frame)
    {
        using var locked = frame.Lock();
        var info = new SKImageInfo(locked.Size.Width, locked.Size.Height, SKColorType.Bgra8888, SKAlphaType.Premul);
        using var bitmap = new SKBitmap();
        bitmap.InstallPixels(info, locked.Address, locked.RowBytes);

        for (var y = 0; y < bitmap.Height; y += 4)
        {
            for (var x = 0; x < bitmap.Width; x += 4)
            {
                var c = bitmap.GetPixel(x, y);
                // Not pure white and not the dark canvas-surround background — i.e. actual page content.
                if ((c.Red < 250 || c.Green < 250 || c.Blue < 250) && (c.Red > 5 || c.Green > 5 || c.Blue > 5))
                    return true;
            }
        }
        return false;
    }
}
