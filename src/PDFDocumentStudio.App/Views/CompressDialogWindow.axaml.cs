using Avalonia.Controls;
using Avalonia.Interactivity;
using PDFDocumentStudio.Pdf.Compression;

namespace PDFDocumentStudio.App.Views;

public sealed record CompressChoice(double MaxSizeMb, CompressionMode Mode);

public partial class CompressDialogWindow : Window
{
    public CompressChoice? Result { get; private set; }

    public CompressDialogWindow()
    {
        InitializeComponent();
    }

    private void OnCompress(object? sender, RoutedEventArgs e)
    {
        var maxSizeMb = SizeCustom.IsChecked == true
            ? (double)(CustomSizeBox.Value ?? 10)
            : Size5.IsChecked == true ? 5.0
            : Size15.IsChecked == true ? 15.0
            : Size20.IsChecked == true ? 20.0
            : 10.0;

        var mode = ModeCombo.SelectedIndex switch
        {
            0 => CompressionMode.Lossless,
            1 => CompressionMode.BestQuality,
            3 => CompressionMode.Maximum,
            _ => CompressionMode.Balanced,
        };

        Result = new CompressChoice(maxSizeMb, mode);
        Close();
    }

    private void OnCancel(object? sender, RoutedEventArgs e)
    {
        Result = null;
        Close();
    }
}
