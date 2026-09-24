namespace PDFDocumentStudio.Core.Geometry;

/// <summary>An axis-aligned rectangle in PDF points, origin bottom-left (X, Y = bottom-left corner).</summary>
public readonly record struct RectD(double X, double Y, double Width, double Height)
{
    public double Left => X;
    public double Right => X + Width;
    public double Bottom => Y;
    public double Top => Y + Height;
    public PointD Center => new(X + Width / 2.0, Y + Height / 2.0);

    public static RectD FromLTRB(double left, double top, double right, double bottom) =>
        new(left, bottom, right - left, top - bottom);

    public RectD Inflate(double dx, double dy) => new(X - dx, Y - dy, Width + 2 * dx, Height + 2 * dy);

    public bool Contains(PointD p) => p.X >= Left && p.X <= Right && p.Y >= Bottom && p.Y <= Top;
}
