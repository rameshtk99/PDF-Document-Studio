using PDFDocumentStudio.Core.Geometry;
using PDFDocumentStudio.Core.Model;
using SkiaSharp;

namespace PDFDocumentStudio.Pdf.Export;

/// <summary>
/// Prepares an image page object for embedding: opacity is always baked into the bitmap's alpha
/// channel, and a rotated image is rasterized losslessly at its local (un-rotated) size and
/// rotated with an expanded canvas — placed at its rotated bounding box thereafter — mirroring
/// the legacy app's PIL-based approach exactly. See docs/LEGACY_FEATURE_INVENTORY.md §2, §6.
/// </summary>
public static class ImageObjectRasterizer
{
    /// <summary>Pixel density used when rasterizing a rotated image at its local size, matching
    /// the legacy app's fixed 4 px/pt so rotated stamps stay crisp at typical print resolution.</summary>
    private const double PxPerPt = 4.0;

    public readonly record struct Placement(byte[] PngBytes, double X, double Y, double Width, double Height);

    public static Placement Prepare(ImagePageObject obj)
    {
        using var original = SKBitmap.Decode(obj.ImagePath)
            ?? throw new InvalidDataException($"Could not decode image '{obj.ImagePath}'.");

        if (obj.Rotation == 0)
        {
            using var withOpacity = ApplyOpacity(original, obj.Opacity);
            return new Placement(Encode(withOpacity), obj.X, obj.Y, obj.Width, obj.Height);
        }

        var localPxW = Math.Max(1, (int)Math.Round(obj.Width * PxPerPt));
        var localPxH = Math.Max(1, (int)Math.Round(obj.Height * PxPerPt));
        using var resized = original.Resize(new SKImageInfo(localPxW, localPxH), SKSamplingOptions.Default);
        using var localBitmap = resized ?? original.Copy();
        using var withOpacityLocal = ApplyOpacity(localBitmap, obj.Opacity);

        var (bboxW, bboxH) = GeometryMath.RotatedBoundingBoxSize(obj.Width, obj.Height, obj.Rotation);
        var bboxPxW = Math.Max(1, (int)Math.Round(bboxW * PxPerPt));
        var bboxPxH = Math.Max(1, (int)Math.Round(bboxH * PxPerPt));

        using var rotatedBitmap = new SKBitmap(bboxPxW, bboxPxH, SKColorType.Rgba8888, SKAlphaType.Unpremul);
        using (var canvas = new SKCanvas(rotatedBitmap))
        {
            canvas.Clear(SKColors.Transparent);
            canvas.Translate(bboxPxW / 2f, bboxPxH / 2f);
            // Positive = clockwise as viewed on this Y-down raster canvas — matches our rotation
            // convention directly (empirically confirmed against PDFsharp's own Y-down space too).
            canvas.RotateDegrees((float)obj.Rotation);
            canvas.Translate(-localPxW / 2f, -localPxH / 2f);
            canvas.DrawBitmap(withOpacityLocal, 0, 0, SKSamplingOptions.Default, paint: null);
        }

        var centerX = obj.X + obj.Width / 2.0;
        var centerY = obj.Y + obj.Height / 2.0;
        return new Placement(Encode(rotatedBitmap), centerX - bboxW / 2.0, centerY - bboxH / 2.0, bboxW, bboxH);
    }

    private static SKBitmap ApplyOpacity(SKBitmap source, double opacityPercent)
    {
        var normalized = source.Copy(SKColorType.Rgba8888) ?? source.Copy();
        if (opacityPercent >= 100.0) return normalized;

        var factor = Math.Clamp(opacityPercent, 0, 100) / 100.0;
        // Object images are stamp/logo-sized in practice, so a per-pixel GetPixel/SetPixel pass
        // is not a bottleneck here — revisit with a raw pixel-span pass if profiling ever says otherwise.
        for (var y = 0; y < normalized.Height; y++)
        {
            for (var x = 0; x < normalized.Width; x++)
            {
                var c = normalized.GetPixel(x, y);
                normalized.SetPixel(x, y, new SKColor(c.Red, c.Green, c.Blue, (byte)(c.Alpha * factor)));
            }
        }
        return normalized;
    }

    private static byte[] Encode(SKBitmap bitmap)
    {
        using var image = SKImage.FromBitmap(bitmap);
        using var data = image.Encode(SKEncodedImageFormat.Png, 100);
        return data.ToArray();
    }
}
