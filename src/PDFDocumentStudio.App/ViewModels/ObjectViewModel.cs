using Avalonia.Media.Imaging;
using CommunityToolkit.Mvvm.ComponentModel;
using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.App.ViewModels;

public sealed partial class ObjectViewModel(PageObject model) : ObservableObject
{
    public PageObject Model { get; } = model;
    public string Id => Model.Id;
    public bool IsText => Model is TextPageObject;
    public bool IsImage => Model is ImagePageObject;

    /// <summary>The page this object lives on — set once when the wrapper is built for a page's
    /// <see cref="PageViewModel.Objects"/> list. Lets selection/gesture code (which only ever
    /// holds an <see cref="ObjectViewModel"/> reference) know which page to make current, without
    /// a global "current page's objects" list to search.</summary>
    public PageViewModel? OwnerPage { get; set; }

    public TextStyle? TextStyle => (Model as TextPageObject)?.Style;
    public string? ImagePath => (Model as ImagePageObject)?.ImagePath;

    [ObservableProperty] private double _left;
    [ObservableProperty] private double _top;
    [ObservableProperty] private double _width;
    [ObservableProperty] private double _height;
    [ObservableProperty] private double _rotationDegrees;
    [ObservableProperty] private double _opacityFraction = 1.0;
    [ObservableProperty] private bool _isSelected;
    [ObservableProperty] private Bitmap? _imageBitmap;

    public void SyncFromModel(double zoom, double pageHeightPt)
    {
        Left = Model.X * zoom;
        Top = (pageHeightPt - Model.Y - Model.Height) * zoom;
        Width = Model.Width * zoom;
        Height = Model.Height * zoom;
        RotationDegrees = Model.Rotation;
        OpacityFraction = Math.Clamp(Model.Opacity, 0, 100) / 100.0;
    }
}
