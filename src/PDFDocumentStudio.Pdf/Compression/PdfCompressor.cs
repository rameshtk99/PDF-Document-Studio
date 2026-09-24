using PdfSharp.Pdf;
using PdfSharp.Pdf.IO;
using SkiaSharp;

namespace PDFDocumentStudio.Pdf.Compression;

public enum CompressionMode { Lossless, BestQuality, Balanced, Maximum }

public sealed record CompressionResult(long OriginalSizeBytes, long FinalSizeBytes, bool TargetReached, IReadOnlyList<string> Notes);

/// <summary>
/// Shrinks an already-exported PDF file (never operates on an in-memory <see cref="Core.Model.EditorDocument"/>
/// directly — matches the legacy pipeline, which always compresses a fully-baked export). A max
/// size is a hard ceiling, never a target: a file already under it is left alone.
/// <para/>
/// Scope note vs. the legacy algorithm (docs/LEGACY_FEATURE_INVENTORY.md §7): without a
/// content-stream interpreter we can't compute an image's true on-page placement/coverage, so
/// candidates are selected by the image's own pixel size instead of page-area coverage, and only
/// JPEG-filtered (/DCTDecode) images are recompressed. The grayscale-safety check (preserving
/// small colored stamps/seals) and the quality ladder are otherwise ported as documented.
/// </summary>
public sealed class PdfCompressor
{
    private static readonly int[] QualityLadder = [75, 72, 70, 68, 60];
    private const int MinImagePixelDimension = 40;
    private const double GrayscaleColorFractionThreshold = 0.0003;

    public CompressionResult Compress(string inputPath, string outputPath, double maxSizeMb, CompressionMode mode)
    {
        var originalSize = new FileInfo(inputPath).Length;
        var maxBytes = (long)(maxSizeMb * 1024 * 1024);
        var notes = new List<string>();

        SaveStructural(inputPath, outputPath);
        var size = new FileInfo(outputPath).Length;
        if (size >= originalSize)
        {
            File.Copy(inputPath, outputPath, overwrite: true);
            size = originalSize;
        }
        notes.Add($"Structural resave: {size:N0} bytes.");

        if (mode == CompressionMode.Lossless || size <= maxBytes)
            return new CompressionResult(originalSize, size, size <= maxBytes, notes);

        var rungs = mode == CompressionMode.BestQuality ? QualityLadder[..2] : QualityLadder;
        var reached = false;

        foreach (var quality in rungs)
        {
            RecompressImages(outputPath, quality, downscale: false);
            size = new FileInfo(outputPath).Length;
            notes.Add($"Quality {quality}: {size:N0} bytes.");
            if (size <= maxBytes)
            {
                reached = true;
                if (mode != CompressionMode.Maximum) break;
            }
        }

        if (!reached)
        {
            RecompressImages(outputPath, QualityLadder[^1], downscale: true);
            size = new FileInfo(outputPath).Length;
            notes.Add($"Downscaled floor: {size:N0} bytes.");
            reached = size <= maxBytes;
            if (!reached) notes.Add("Could not safely reduce below the target size without risking readability.");
        }

        ValidatePageCount(inputPath, outputPath);
        return new CompressionResult(originalSize, size, reached, notes);
    }

    private static void SaveStructural(string inputPath, string outputPath)
    {
        using var doc = PdfReader.Open(inputPath, PdfDocumentOpenMode.Modify);
        doc.Options.CompressContentStreams = true;
        doc.Options.FlateEncodeMode = PdfFlateEncodeMode.BestCompression;
        doc.Save(outputPath);
    }

    private static void RecompressImages(string path, int quality, bool downscale)
    {
        using var doc = PdfReader.Open(path, PdfDocumentOpenMode.Modify);
        foreach (var page in doc.Pages)
        {
            var xobjects = page.Resources.Elements.GetDictionary("/XObject");
            if (xobjects is null) continue;

            foreach (var key in xobjects.Elements.Keys.ToList())
            {
                try
                {
                    if (xobjects.Elements.GetObject(key) is not PdfDictionary imageDict) continue;
                    if (imageDict.Elements.GetName("/Subtype") != "/Image") continue;
                    if (GetFilterName(imageDict) != "/DCTDecode") continue;

                    var width = imageDict.Elements.GetInteger("/Width");
                    var height = imageDict.Elements.GetInteger("/Height");
                    if (width < MinImagePixelDimension || height < MinImagePixelDimension) continue;

                    RecompressOne(imageDict, quality, downscale);
                }
                catch (Exception)
                {
                    // Unexpected XObject structure — leave this image untouched rather than abort.
                }
            }
        }
        doc.Save(path);
    }

    private static string? GetFilterName(PdfDictionary imageDict)
    {
        var value = imageDict.Elements.GetValue("/Filter");
        return value switch
        {
            PdfName name => name.Value,
            PdfArray arr when arr.Elements.Count > 0 => (arr.Elements[^1] as PdfName)?.Value,
            _ => null,
        };
    }

    private static void RecompressOne(PdfDictionary imageDict, int quality, bool downscale)
    {
        var raw = imageDict.Stream.Value;
        using var bitmap = SKBitmap.Decode(raw);
        if (bitmap is null) return;

        using var working = downscale
            ? bitmap.Resize(new SKImageInfo((int)(bitmap.Width * 0.75), (int)(bitmap.Height * 0.75)), SKSamplingOptions.Default) ?? bitmap.Copy()
            : bitmap.Copy();

        var grayscaleSafe = IsGrayscaleSafe(working);
        using var finalBitmap = grayscaleSafe ? ToGrayscale(working) : working.Copy();

        using var image = SKImage.FromBitmap(finalBitmap);
        using var data = image.Encode(SKEncodedImageFormat.Jpeg, quality);
        var newBytes = data.ToArray();
        if (newBytes.Length >= raw.Length) return; // never grow an image

        imageDict.Stream.Value = newBytes;
        imageDict.Elements.SetInteger("/Width", finalBitmap.Width);
        imageDict.Elements.SetInteger("/Height", finalBitmap.Height);
        imageDict.Elements.SetName("/Filter", "/DCTDecode");
        imageDict.Elements.SetInteger("/BitsPerComponent", 8);
        imageDict.Elements.SetName("/ColorSpace", grayscaleSafe ? "/DeviceGray" : "/DeviceRGB");
        imageDict.Elements.Remove("/DecodeParms");
        imageDict.Elements.Remove("/Decode");
    }

    /// <summary>Fraction-of-colored-pixels check, not a whole-image color average — an average
    /// dilutes a small colored stamp/seal to near-zero and wrongly greenlights grayscale.</summary>
    private static bool IsGrayscaleSafe(SKBitmap bitmap)
    {
        using var thumb = bitmap.Resize(
            new SKImageInfo(Math.Min(500, bitmap.Width), Math.Min(500, bitmap.Height)), SKSamplingOptions.Default) ?? bitmap.Copy();

        var total = thumb.Width * thumb.Height;
        if (total == 0) return false;

        var colored = 0;
        for (var y = 0; y < thumb.Height; y++)
        {
            for (var x = 0; x < thumb.Width; x++)
            {
                var c = thumb.GetPixel(x, y);
                var diff = Math.Abs(c.Red - c.Green) + Math.Abs(c.Green - c.Blue) + Math.Abs(c.Red - c.Blue);
                if (diff > 12) colored++;
            }
        }
        return (double)colored / total < GrayscaleColorFractionThreshold;
    }

    private static SKBitmap ToGrayscale(SKBitmap source)
    {
        var result = new SKBitmap(source.Width, source.Height, SKColorType.Rgba8888, SKAlphaType.Opaque);
        using var canvas = new SKCanvas(result);
        using var paint = new SKPaint
        {
            ColorFilter = SKColorFilter.CreateColorMatrix(
            [
                0.299f, 0.587f, 0.114f, 0, 0,
                0.299f, 0.587f, 0.114f, 0, 0,
                0.299f, 0.587f, 0.114f, 0, 0,
                0, 0, 0, 1, 0,
            ]),
        };
        canvas.DrawBitmap(source, 0, 0, SKSamplingOptions.Default, paint);
        return result;
    }

    private static void ValidatePageCount(string inputPath, string outputPath)
    {
        using var a = PdfReader.Open(inputPath, PdfDocumentOpenMode.Import);
        using var b = PdfReader.Open(outputPath, PdfDocumentOpenMode.Import);
        if (a.PageCount != b.PageCount)
            throw new InvalidOperationException("Compression changed the page count — aborting.");
    }
}
