namespace PDFDocumentStudio.Core.Geometry;

/// <summary>
/// Shared rotation/hit-test/resize math for page objects.
/// Convention (matches the legacy app): rotation is in degrees, clockwise as the user views the page,
/// about the object's own center, in a Y-up (PDF point) coordinate space.
/// </summary>
public static class GeometryMath
{
    /// <summary>Rotates a point given in the object's local (un-rotated) frame into world space.</summary>
    public static PointD LocalToWorld(PointD local, PointD pivot, double rotationDegrees)
    {
        if (rotationDegrees == 0) return pivot + local;
        var rad = rotationDegrees * Math.PI / 180.0;
        var cos = Math.Cos(rad);
        var sin = Math.Sin(rad);
        var x = local.X * cos + local.Y * sin;
        var y = -local.X * sin + local.Y * cos;
        return pivot + new PointD(x, y);
    }

    /// <summary>Inverse of <see cref="LocalToWorld"/>: maps a world-space point into the object's local frame.</summary>
    public static PointD WorldToLocal(PointD world, PointD pivot, double rotationDegrees)
    {
        if (rotationDegrees == 0) return world - pivot;
        var d = world - pivot;
        var rad = -rotationDegrees * Math.PI / 180.0;
        var cos = Math.Cos(rad);
        var sin = Math.Sin(rad);
        var x = d.X * cos + d.Y * sin;
        var y = -d.X * sin + d.Y * cos;
        return new PointD(x, y);
    }

    /// <summary>True if <paramref name="worldPoint"/> falls inside a rectangle of the given local size,
    /// centered at <paramref name="pivot"/> and rotated by <paramref name="rotationDegrees"/>.</summary>
    public static bool HitTestRotatedRect(PointD worldPoint, RectD localRect, PointD pivot, double rotationDegrees)
    {
        var local = WorldToLocal(worldPoint, pivot, rotationDegrees);
        return localRect.Contains(local);
    }

    /// <summary>Size of the smallest axis-aligned box that fully contains a <paramref name="width"/>x<paramref name="height"/>
    /// rectangle rotated by <paramref name="rotationDegrees"/> about its own center. Used when rasterizing a rotated
    /// image/text object at its local size before rotating the bitmap losslessly.</summary>
    public static (double Width, double Height) RotatedBoundingBoxSize(double width, double height, double rotationDegrees)
    {
        var rad = rotationDegrees * Math.PI / 180.0;
        var cos = Math.Abs(Math.Cos(rad));
        var sin = Math.Abs(Math.Sin(rad));
        return (width * cos + height * sin, width * sin + height * cos);
    }

    /// <summary>The eight resize-handle positions, in the object's local (un-rotated) frame, for a rect at the origin.</summary>
    public static IReadOnlyDictionary<ResizeHandle, PointD> HandlePositions(double width, double height)
    {
        var hw = width / 2.0;
        var hh = height / 2.0;
        return new Dictionary<ResizeHandle, PointD>
        {
            [ResizeHandle.TopLeft] = new(-hw, hh),
            [ResizeHandle.Top] = new(0, hh),
            [ResizeHandle.TopRight] = new(hw, hh),
            [ResizeHandle.Right] = new(hw, 0),
            [ResizeHandle.BottomRight] = new(hw, -hh),
            [ResizeHandle.Bottom] = new(0, -hh),
            [ResizeHandle.BottomLeft] = new(-hw, -hh),
            [ResizeHandle.Left] = new(-hw, 0),
        };
    }

    /// <summary>
    /// Computes a new local rect (relative to the object's un-rotated top-left origin at (0,0)) when the given
    /// handle is dragged by <paramref name="localDelta"/> (already expressed in the object's local, un-rotated frame).
    /// The opposite handle stays fixed, matching the legacy drag-resize behavior. Corner handles honor
    /// <paramref name="lockAspectRatio"/> (Shift-drag) by scaling both axes by the dominant delta.
    /// </summary>
    public static RectD ResizeFromHandle(
        double width, double height, ResizeHandle handle, PointD localDelta,
        double minSize, bool lockAspectRatio)
    {
        double left = 0, top = 0, right = width, bottom = height;

        switch (handle)
        {
            case ResizeHandle.Left: left += localDelta.X; break;
            case ResizeHandle.Right: right += localDelta.X; break;
            case ResizeHandle.Top: top += localDelta.Y; break;
            case ResizeHandle.Bottom: bottom += localDelta.Y; break;
            case ResizeHandle.TopLeft: left += localDelta.X; top += localDelta.Y; break;
            case ResizeHandle.TopRight: right += localDelta.X; top += localDelta.Y; break;
            case ResizeHandle.BottomLeft: left += localDelta.X; bottom += localDelta.Y; break;
            case ResizeHandle.BottomRight: right += localDelta.X; bottom += localDelta.Y; break;
        }

        if (lockAspectRatio && IsCorner(handle) && width > 0 && height > 0)
        {
            var newW = right - left;
            var newH = bottom - top;
            var aspect = width / height;
            // Drive by whichever axis moved more, keep the anchor corner fixed.
            if (Math.Abs(newW - width) >= Math.Abs(newH - height))
            {
                newH = newW / aspect;
            }
            else
            {
                newW = newH * aspect;
            }

            switch (handle)
            {
                case ResizeHandle.TopLeft: left = right - newW; top = bottom - newH; break;
                case ResizeHandle.TopRight: right = left + newW; top = bottom - newH; break;
                case ResizeHandle.BottomLeft: left = right - newW; bottom = top + newH; break;
                case ResizeHandle.BottomRight: right = left + newW; bottom = top + newH; break;
            }
        }

        if (right - left < minSize)
        {
            if (handle is ResizeHandle.Left or ResizeHandle.TopLeft or ResizeHandle.BottomLeft) left = right - minSize;
            else right = left + minSize;
        }
        if (bottom - top < minSize)
        {
            if (handle is ResizeHandle.Top or ResizeHandle.TopLeft or ResizeHandle.TopRight) top = bottom - minSize;
            else bottom = top + minSize;
        }

        return RectD.FromLTRB(left, top, right, bottom);
    }

    private static bool IsCorner(ResizeHandle h) =>
        h is ResizeHandle.TopLeft or ResizeHandle.TopRight or ResizeHandle.BottomLeft or ResizeHandle.BottomRight;
}

public enum ResizeHandle
{
    TopLeft, Top, TopRight, Right, BottomRight, Bottom, BottomLeft, Left
}
