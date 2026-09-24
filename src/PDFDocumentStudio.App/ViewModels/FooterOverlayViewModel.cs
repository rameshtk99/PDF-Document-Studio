using CommunityToolkit.Mvvm.ComponentModel;

namespace PDFDocumentStudio.App.ViewModels;

public sealed partial class FooterLineViewModel(string text, double left, double top, string fontName, double fontSize) : ObservableObject
{
    public string Text { get; } = text;
    public double Left { get; } = left;
    public double Top { get; } = top;
    public string FontName { get; } = fontName;
    public double FontSize { get; } = fontSize;
}

public readonly record struct FooterGridSegment(double X1, double Y1, double X2, double Y2);

public sealed partial class FooterOverlayViewModel : ObservableObject
{
    [ObservableProperty] private bool _visible;
    [ObservableProperty] private double _zoneTop;
    [ObservableProperty] private double _zoneHeight;
    [ObservableProperty] private bool _contentCompressed;
    [ObservableProperty] private FooterLineViewModel[] _lines = [];
    [ObservableProperty] private FooterGridSegment[] _gridLines = [];
}
