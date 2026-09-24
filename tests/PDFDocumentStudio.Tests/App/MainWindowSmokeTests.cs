using Avalonia.Headless.XUnit;
using Avalonia.Threading;
using PDFDocumentStudio.App;

namespace PDFDocumentStudio.Tests.App;

/// <summary>
/// Constructs the real window and pumps layout, catching runtime XAML binding failures (bad
/// property paths, converter lookups, etc.) that compile-time XAML compilation can miss — this
/// caught nothing today, but it's cheap insurance for the per-page canvas bindings
/// (Owner/TextLayout/Objects/Footer bound through #RootWindow.DataContext on every page item).
/// </summary>
public class MainWindowSmokeTests
{
    private static string SamplePdfPath => Path.Combine(AppContext.BaseDirectory, "Assets", "sample.pdf");

    [AvaloniaFact]
    public void MainWindow_OpensDocumentAndRendersEveryPageWithoutError()
    {
        var window = new MainWindow();
        window.Show();

        var vm = (PDFDocumentStudio.App.ViewModels.MainViewModel)window.DataContext!;
        vm.LoadPdf(SamplePdfPath);

        Dispatcher.UIThread.RunJobs();
        window.UpdateLayout();

        Assert.True(vm.Pages.Count > 1);

        vm.FooterRows[0].Cells[0].Text = "Confidential";
        vm.ApplyFooterToAllPages();
        Dispatcher.UIThread.RunJobs();
        window.UpdateLayout();

        Assert.All(vm.Pages, p => Assert.True(p.FooterOverlay.Visible));

        vm.AddTextToCurrentPage();
        Dispatcher.UIThread.RunJobs();
        window.UpdateLayout();

        Assert.NotNull(vm.SelectedObject);
        Assert.True(vm.SelectedObject!.IsSelected);

        window.Close();
    }

    /// <summary>
    /// Regression test for a real bug found via manual testing: eagerly requesting full-resolution
    /// bitmaps for every page (and again for every page on every zoom step) floods the renderer
    /// with far more work than it can keep up with on a longer document, so most pages never get a
    /// bitmap at all and the canvas renders blank. The fix requests bitmaps only for pages near the
    /// viewport (driven by ScrollViewer.ScrollChanged). This asserts the actually-visible page gets
    /// a bitmap promptly both after load and after zooming — the failure mode was it never arriving.
    /// </summary>
    [AvaloniaFact]
    public async Task VisiblePageGetsBitmapPromptly_AfterLoadAndAfterZoom()
    {
        var window = new MainWindow();
        window.Show();
        var vm = (PDFDocumentStudio.App.ViewModels.MainViewModel)window.DataContext!;
        vm.LoadPdf(SamplePdfPath);
        Dispatcher.UIThread.RunJobs();
        window.UpdateLayout();

        for (var i = 0; i < 50 && vm.Pages[0].Bitmap is null; i++)
        {
            await Task.Delay(50);
            Dispatcher.UIThread.RunJobs();
        }
        Assert.NotNull(vm.Pages[0].Bitmap);

        vm.ZoomIn();
        vm.ZoomIn();
        Dispatcher.UIThread.RunJobs();
        window.UpdateLayout();
        // The zoom-triggered re-render at the new DPI is async; the page must keep showing its
        // previous bitmap meanwhile — it must never go back to null.
        Assert.NotNull(vm.Pages[0].Bitmap);

        for (var i = 0; i < 50; i++)
        {
            await Task.Delay(50);
            Dispatcher.UIThread.RunJobs();
            window.UpdateLayout();
        }
        Assert.NotNull(vm.Pages[0].Bitmap);

        window.Close();
    }
}
