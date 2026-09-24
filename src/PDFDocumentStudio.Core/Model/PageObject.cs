using System.Text.Json.Serialization;

namespace PDFDocumentStudio.Core.Model;

/// <summary>
/// A single editable overlay item placed on a page: an image stamp or a text box. Extensible by
/// adding further subclasses (e.g. a future shape/watermark object) without touching the editor's
/// selection/move/resize/rotate/undo machinery, which all operate against this base type.
/// </summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type")]
[JsonDerivedType(typeof(ImagePageObject), "image")]
[JsonDerivedType(typeof(TextPageObject), "text")]
public abstract class PageObject
{
    public string Id { get; set; } = Guid.NewGuid().ToString();

    /// <summary>1-based display page position. Kept in sync by every page-order mutation.</summary>
    public int PageNumber { get; set; }

    /// <summary>Bottom-left X, in PDF points, of the object's un-rotated local rect.</summary>
    public double X { get; set; }

    /// <summary>Bottom-left Y, in PDF points, of the object's un-rotated local rect.</summary>
    public double Y { get; set; }

    public double Width { get; set; }
    public double Height { get; set; }

    /// <summary>Degrees, clockwise as viewed, about the object's own center. See <see cref="Geometry.GeometryMath"/>.</summary>
    public double Rotation { get; set; }

    /// <summary>Percentage, 0-100.</summary>
    public double Opacity { get; set; } = 100.0;

    /// <summary>Paint/hit-test order; lower is further back. Not necessarily dense/contiguous.</summary>
    public int ZIndex { get; set; }

    public bool Locked { get; set; }
    public bool Visible { get; set; } = true;

    /// <summary>Null = ungrouped. A shared value links objects (possibly of mixed kinds, across the
    /// same page) into one group for selection/move/resize/rotate purposes.</summary>
    public string? GroupId { get; set; }

    public Geometry.PointD Center => new(X + Width / 2.0, Y + Height / 2.0);

    public abstract PageObject Clone();

    protected void CopyBaseTo(PageObject target)
    {
        target.Id = Id;
        target.PageNumber = PageNumber;
        target.X = X;
        target.Y = Y;
        target.Width = Width;
        target.Height = Height;
        target.Rotation = Rotation;
        target.Opacity = Opacity;
        target.ZIndex = ZIndex;
        target.Locked = Locked;
        target.Visible = Visible;
        target.GroupId = GroupId;
    }
}

public sealed class ImagePageObject : PageObject
{
    /// <summary>Absolute path to the source image file. A path reference, not embedded bytes —
    /// matches the legacy app; see docs/LEGACY_FEATURE_INVENTORY.md §6 for the portability tradeoff.</summary>
    public required string ImagePath { get; set; }

    /// <summary>"marquee" for a captured page snippet, null for a user-added image/stamp.</summary>
    public string? Source { get; set; }

    public override PageObject Clone()
    {
        var clone = new ImagePageObject { ImagePath = ImagePath, Source = Source };
        CopyBaseTo(clone);
        return clone;
    }
}

public sealed class TextPageObject : PageObject
{
    public TextStyle Style { get; set; } = new();

    public override PageObject Clone()
    {
        var clone = new TextPageObject { Style = Style };
        CopyBaseTo(clone);
        return clone;
    }
}
