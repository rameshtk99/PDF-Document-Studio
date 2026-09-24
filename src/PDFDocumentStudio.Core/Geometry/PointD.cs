namespace PDFDocumentStudio.Core.Geometry;

/// <summary>A point in PDF coordinate space (points, origin bottom-left, Y-up).</summary>
public readonly record struct PointD(double X, double Y)
{
    public static PointD operator +(PointD a, PointD b) => new(a.X + b.X, a.Y + b.Y);
    public static PointD operator -(PointD a, PointD b) => new(a.X - b.X, a.Y - b.Y);
    public static PointD operator *(PointD a, double scale) => new(a.X * scale, a.Y * scale);
}
