using PDFDocumentStudio.Core.Geometry;

namespace PDFDocumentStudio.Tests.Core;

public class GeometryMathTests
{
    [Fact]
    public void LocalToWorld_NoRotation_IsJustTranslation()
    {
        var world = GeometryMath.LocalToWorld(new PointD(5, 5), new PointD(10, 10), 0);
        Assert.Equal(15, world.X, 3);
        Assert.Equal(15, world.Y, 3);
    }

    [Fact]
    public void LocalToWorld_90Degrees_RotatesClockwiseAsViewed()
    {
        // A point to the right of the pivot should end up below it after a 90deg clockwise turn.
        var world = GeometryMath.LocalToWorld(new PointD(1, 0), new PointD(0, 0), 90);
        Assert.Equal(0, world.X, 3);
        Assert.Equal(-1, world.Y, 3);
    }

    [Fact]
    public void WorldToLocal_IsInverseOfLocalToWorld()
    {
        var pivot = new PointD(3, 7);
        var local = new PointD(2, -4);
        var world = GeometryMath.LocalToWorld(local, pivot, 37);
        var roundTrip = GeometryMath.WorldToLocal(world, pivot, 37);
        Assert.Equal(local.X, roundTrip.X, 3);
        Assert.Equal(local.Y, roundTrip.Y, 3);
    }

    [Fact]
    public void HitTestRotatedRect_PointInsideUnrotated_ReturnsTrue()
    {
        var rect = new RectD(-5, -5, 10, 10);
        Assert.True(GeometryMath.HitTestRotatedRect(new PointD(12, 10), rect, new PointD(10, 10), 0));
    }

    [Fact]
    public void HitTestRotatedRect_PointOutsideRotated_ReturnsFalse()
    {
        var rect = new RectD(-5, -5, 10, 10);
        Assert.False(GeometryMath.HitTestRotatedRect(new PointD(0, 0), rect, new PointD(10, 10), 45));
    }

    [Theory]
    [InlineData(0, 10, 10)]
    [InlineData(90, 10, 10)]
    public void RotatedBoundingBoxSize_AxisAligned_MatchesOriginalOrSwapped(double rotation, double w, double h)
    {
        var (bw, bh) = GeometryMath.RotatedBoundingBoxSize(w, h, rotation);
        Assert.Equal(w, bw, 3);
        Assert.Equal(h, bh, 3);
    }

    [Fact]
    public void ResizeFromHandle_BottomRight_KeepsTopLeftFixed()
    {
        // Y-up, bottom-left-origin local frame (matches PageObject.X/Y directly) — "Top" is the
        // larger Y value, so the handle opposite BottomRight (i.e. TopLeft) keeps Left=0, Top=height.
        var rect = GeometryMath.ResizeFromHandle(100, 50, ResizeHandle.BottomRight, new PointD(20, 10), minSize: 5, lockAspectRatio: false);
        Assert.Equal(0, rect.Left, 3);
        Assert.Equal(50, rect.Top, 3);
        Assert.Equal(120, rect.Right, 3);
        Assert.Equal(10, rect.Bottom, 3);
    }

    [Fact]
    public void ResizeFromHandle_NeverShrinksBelowMinSize()
    {
        var rect = GeometryMath.ResizeFromHandle(100, 50, ResizeHandle.Right, new PointD(-99, 0), minSize: 5, lockAspectRatio: false);
        Assert.Equal(5, rect.Right - rect.Left, 3);
    }

    [Fact]
    public void ResizeObjectRect_Unrotated_MatchesPlainResizeFromHandle()
    {
        var center = new PointD(50, 25); // width=100,height=50 centered here -> bottom-left (0,0)
        var (x, y, w, h) = GeometryMath.ResizeObjectRect(center, 100, 50, 0, ResizeHandle.Right, new PointD(20, 0), minSize: 5, lockAspectRatio: false);

        Assert.Equal(0, x, 3);
        Assert.Equal(0, y, 3);
        Assert.Equal(120, w, 3);
        Assert.Equal(50, h, 3);
    }

    [Fact]
    public void ResizeObjectRect_Rotated180_RightHandleDragMovesLeftEdgeInWorldSpace()
    {
        // A 180-degree-rotated object's local "Right" handle points toward world -X, so dragging
        // it in +X world space should shrink the object from its (world) left edge.
        var center = new PointD(50, 25);
        var (x, _, w, _) = GeometryMath.ResizeObjectRect(center, 100, 50, 180, ResizeHandle.Right, new PointD(20, 0), minSize: 5, lockAspectRatio: false);

        Assert.Equal(80, w, 3); // shrunk, not grown
        Assert.Equal(20, x, 3); // left edge moved right by 20
    }
}
