using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Core.Commands;

/// <summary>Captures a PageObject's mutable geometry/paint state so a command can restore it exactly
/// on undo, regardless of which properties actually changed.</summary>
public readonly record struct ObjectSnapshot(
    double X, double Y, double Width, double Height,
    double Rotation, double Opacity, int ZIndex, string? GroupId)
{
    public static ObjectSnapshot Of(PageObject obj) =>
        new(obj.X, obj.Y, obj.Width, obj.Height, obj.Rotation, obj.Opacity, obj.ZIndex, obj.GroupId);

    public void ApplyTo(PageObject obj)
    {
        obj.X = X; obj.Y = Y; obj.Width = Width; obj.Height = Height;
        obj.Rotation = Rotation; obj.Opacity = Opacity; obj.ZIndex = ZIndex; obj.GroupId = GroupId;
    }
}
