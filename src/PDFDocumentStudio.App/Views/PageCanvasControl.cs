using System.Collections.Specialized;
using System.ComponentModel;
using System.Globalization;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Media;
using PDFDocumentStudio.App.ViewModels;
using PDFDocumentStudio.Core.Geometry;
using PDFDocumentStudio.Core.TextLayout;

namespace PDFDocumentStudio.App.Views;

/// <summary>
/// Draws one page (background bitmap, footer, page objects) and handles select/move/resize/rotate
/// directly via DrawingContext + pointer events. One instance is created per page in the document's
/// continuous list — every page is always visible and independently interactive, not just whichever
/// page happens to be "current". Talks back to the view model through <see cref="Owner"/> (bound to
/// the window's DataContext) rather than bubbling custom CLR events, since there are many instances
/// of this control alive at once, one per page.
/// </summary>
public sealed class PageCanvasControl : Control
{
    private const double HandleHitRadius = 7.0;
    private const double HandleVisualSize = 8.0;
    private const double RotateHandleOffsetPx = 26.0;

    public static readonly StyledProperty<PageViewModel?> PageProperty =
        AvaloniaProperty.Register<PageCanvasControl, PageViewModel?>(nameof(Page));

    public static readonly StyledProperty<double> ScreenScaleProperty =
        AvaloniaProperty.Register<PageCanvasControl, double>(nameof(ScreenScale), 1.0);

    public static readonly StyledProperty<FooterOverlayViewModel?> FooterProperty =
        AvaloniaProperty.Register<PageCanvasControl, FooterOverlayViewModel?>(nameof(Footer));

    public static readonly StyledProperty<IReadOnlyList<ObjectViewModel>?> ObjectsProperty =
        AvaloniaProperty.Register<PageCanvasControl, IReadOnlyList<ObjectViewModel>?>(nameof(Objects));

    public static readonly StyledProperty<MainViewModel?> OwnerProperty =
        AvaloniaProperty.Register<PageCanvasControl, MainViewModel?>(nameof(Owner));

    public static readonly StyledProperty<TextLayoutEngine?> TextLayoutProperty =
        AvaloniaProperty.Register<PageCanvasControl, TextLayoutEngine?>(nameof(TextLayout));

    public PageViewModel? Page { get => GetValue(PageProperty); set => SetValue(PageProperty, value); }
    public double ScreenScale { get => GetValue(ScreenScaleProperty); set => SetValue(ScreenScaleProperty, value); }
    public FooterOverlayViewModel? Footer { get => GetValue(FooterProperty); set => SetValue(FooterProperty, value); }
    public IReadOnlyList<ObjectViewModel>? Objects { get => GetValue(ObjectsProperty); set => SetValue(ObjectsProperty, value); }
    public MainViewModel? Owner { get => GetValue(OwnerProperty); set => SetValue(OwnerProperty, value); }
    public TextLayoutEngine? TextLayout { get => GetValue(TextLayoutProperty); set => SetValue(TextLayoutProperty, value); }

    private enum DragMode { None, Move, Resize, Rotate }

    private DragMode _mode = DragMode.None;
    private ObjectViewModel? _activeObject;
    private ResizeHandle _activeHandle;
    private Point? _lastPointerPos;
    private double _rotateStartAngleDeg;
    private double _rotateStartRotationDeg;

    static PageCanvasControl()
    {
        AffectsRender<PageCanvasControl>(PageProperty, ScreenScaleProperty, FooterProperty, ObjectsProperty);
    }

    public PageCanvasControl()
    {
        PropertyChanged += OnAnyPropertyChanged;
    }

    private void OnAnyPropertyChanged(object? sender, AvaloniaPropertyChangedEventArgs e)
    {
        if (e.Property == ObjectsProperty) RebindObjects(e.OldValue as IReadOnlyList<ObjectViewModel>, e.NewValue as IReadOnlyList<ObjectViewModel>);
        else if (e.Property == PageProperty) RebindPage(e.OldValue as PageViewModel, e.NewValue as PageViewModel);
        else if (e.Property == FooterProperty) RebindFooter(e.OldValue as FooterOverlayViewModel, e.NewValue as FooterOverlayViewModel);
    }

    /// <summary>Same reasoning as <see cref="RebindPage"/>: the footer overlay is one stable
    /// instance per page whose properties are updated in place (footer applied, draft edited,
    /// zoomed) — without this, a footer change would compute correctly but never actually repaint.</summary>
    private void RebindFooter(FooterOverlayViewModel? oldFooter, FooterOverlayViewModel? newFooter)
    {
        if (oldFooter is not null) oldFooter.PropertyChanged -= OnPagePropertyChanged;
        if (newFooter is not null) newFooter.PropertyChanged += OnPagePropertyChanged;
        InvalidateVisual();
    }

    /// <summary>The page's Bitmap/ThumbnailBitmap/DisplayWidth/etc. update asynchronously (a
    /// background render completing, a zoom resize) well after this control's Page property was
    /// first bound — without this subscription, Render() would keep reading a stale value forever
    /// because nothing ever asked Avalonia to repaint, even though the data itself was correct.</summary>
    private void RebindPage(PageViewModel? oldPage, PageViewModel? newPage)
    {
        if (oldPage is not null) oldPage.PropertyChanged -= OnPagePropertyChanged;
        if (newPage is not null) newPage.PropertyChanged += OnPagePropertyChanged;
        InvalidateVisual();
    }

    private void OnPagePropertyChanged(object? sender, PropertyChangedEventArgs e) => InvalidateVisual();

    private void RebindObjects(IReadOnlyList<ObjectViewModel>? oldList, IReadOnlyList<ObjectViewModel>? newList)
    {
        if (oldList is INotifyCollectionChanged oldNotify) oldNotify.CollectionChanged -= OnObjectsCollectionChanged;
        if (oldList is not null) foreach (var o in oldList) o.PropertyChanged -= OnObjectPropertyChanged;

        if (newList is INotifyCollectionChanged newNotify) newNotify.CollectionChanged += OnObjectsCollectionChanged;
        if (newList is not null) foreach (var o in newList) o.PropertyChanged += OnObjectPropertyChanged;

        InvalidateVisual();
    }

    private void OnObjectsCollectionChanged(object? sender, NotifyCollectionChangedEventArgs e)
    {
        if (e.OldItems is not null) foreach (ObjectViewModel o in e.OldItems) o.PropertyChanged -= OnObjectPropertyChanged;
        if (e.NewItems is not null) foreach (ObjectViewModel o in e.NewItems) o.PropertyChanged += OnObjectPropertyChanged;
        InvalidateVisual();
    }

    private void OnObjectPropertyChanged(object? sender, PropertyChangedEventArgs e) => InvalidateVisual();

    public override void Render(DrawingContext context)
    {
        var page = Page;
        if (page is null) return;

        var bounds = new Rect(0, 0, page.DisplayWidth, page.DisplayHeight);
        if (page.Bitmap is { } bitmap) context.DrawImage(bitmap, bounds);
        else
        {
            // The full-resolution bitmap is requested lazily (see MainWindow's viewport-driven
            // loading) and may take a moment, especially on a large/complex page — fall back to
            // the cheap thumbnail (already rendered for every page up front) stretched to size,
            // rather than a blank white rectangle with no visible progress. Soft/blurry until the
            // sharp bitmap arrives, but never actually blank.
            context.FillRectangle(Brushes.White, bounds, 0f);
            if (page.ThumbnailBitmap is { } thumb) context.DrawImage(thumb, bounds);
        }

        if (Footer is { Visible: true } footer)
        {
            // WYSIWYG with the exported PDF: solid text + solid borders only, matching
            // DocumentExporter.DrawFooterTable exactly — no dashed "editor affordance" decoration
            // that would show up as unrelated dotted marks on the page.
            var gridPen = new Pen(Brushes.Black, 0.75);
            foreach (var seg in footer.GridLines)
                context.DrawLine(gridPen, new Point(seg.X1, seg.Y1), new Point(seg.X2, seg.Y2));

            foreach (var line in footer.Lines)
            {
                var ft = new FormattedText(line.Text, CultureInfo.CurrentCulture, FlowDirection.LeftToRight,
                    new Typeface(line.FontName), line.FontSize, Brushes.Black);
                context.DrawText(ft, new Point(line.Left, line.Top));
            }
        }

        var objects = Objects;
        if (objects is not null)
        {
            foreach (var obj in objects)
            {
                using var opacity = context.PushOpacity(obj.OpacityFraction);
                DrawingContext.PushedState? rotation = null;
                if (obj.RotationDegrees != 0)
                {
                    var center = new Point(obj.Left + obj.Width / 2, obj.Top + obj.Height / 2);
                    rotation = context.PushTransform(Matrix.CreateRotation(Matrix.ToRadians(obj.RotationDegrees), center));
                }

                if (obj.IsImage && obj.ImageBitmap is { } img)
                {
                    context.DrawImage(img, new Rect(obj.Left, obj.Top, obj.Width, obj.Height));
                }
                else if (obj.IsText && obj.TextStyle is { } style && TextLayout is not null)
                {
                    DrawText(context, obj, style);
                }

                if (obj.IsSelected)
                {
                    context.DrawRectangle(null, new Pen(Brushes.DodgerBlue, 1.5),
                        new Rect(obj.Left, obj.Top, obj.Width, obj.Height), 0, 0, default);
                }

                rotation?.Dispose();
            }

            var selected = objects.FirstOrDefault(o => o.IsSelected);
            if (selected is not null) DrawHandles(context, selected);
        }
    }

    private void DrawHandles(DrawingContext context, ObjectViewModel obj)
    {
        var (handles, rotateHandle) = GetHandlePositions(obj);
        var fill = Brushes.White;
        var pen = new Pen(Brushes.DodgerBlue, 1.5);
        var half = HandleVisualSize / 2.0;

        foreach (var pos in handles.Values)
            context.DrawRectangle(fill, pen, new Rect(pos.X - half, pos.Y - half, HandleVisualSize, HandleVisualSize), 0, 0, default);

        context.DrawEllipse(fill, pen, rotateHandle, half, half);
    }

    private void DrawText(DrawingContext context, ObjectViewModel obj, Core.Model.TextStyle style)
    {
        var layout = TextLayout!.Layout(style, obj.Width / ScreenScale);
        var brush = new SolidColorBrush(TryParseColor(style.Color, out var color) ? color : Colors.Black);
        const double ascentRatio = 0.8; // must match TextLayoutEngine's ascent approximation

        foreach (var line in layout.Lines)
        {
            if (line.Text.Length == 0) continue;
            var topOfLinePt = line.BaselineFromTop - style.FontSize * ascentRatio;
            var x = obj.Left + line.X * ScreenScale;
            var y = obj.Top + topOfLinePt * ScreenScale;
            var ft = new FormattedText(line.Text, CultureInfo.CurrentCulture, FlowDirection.LeftToRight,
                new Typeface(style.FontName), style.FontSize * ScreenScale, brush);
            context.DrawText(ft, new Point(x, y));
        }
    }

    private static bool TryParseColor(string hex, out Color color)
    {
        try { color = Color.Parse(hex); return true; }
        catch (Exception) { color = Colors.Black; return false; }
    }

    protected override void OnPointerPressed(PointerPressedEventArgs e)
    {
        base.OnPointerPressed(e);
        var page = Page;
        if (page is null) return;

        // Clicking anywhere on a page — including blank canvas, not just an object — makes it the
        // current page, so Add Text/Add Image and the footer's "current page" scope always target
        // whatever the user is actually looking at, without a separate mode switch.
        Owner?.SetCurrentPage(page);

        var pos = e.GetPosition(this);
        var pointerProps = e.GetCurrentPoint(this).Properties;

        if (pointerProps.IsRightButtonPressed)
        {
            // Select whatever's under the cursor (if anything) and let the ContextMenu open
            // normally — never start a move/resize/rotate gesture on a right-click.
            var rightHit = HitTest(pos);
            if (rightHit is not null) Owner?.SelectObject(rightHit);
            return;
        }

        if (!pointerProps.IsLeftButtonPressed) return;

        var selected = (Objects ?? []).FirstOrDefault(o => o.IsSelected);

        if (selected is not null)
        {
            var (handles, rotatePoint) = GetHandlePositions(selected);
            if (Distance(pos, rotatePoint) <= HandleHitRadius)
            {
                BeginGesture(selected, DragMode.Rotate, default, pos);
                _rotateStartAngleDeg = AngleFromPivotDeg(selected, pos);
                _rotateStartRotationDeg = selected.Model.Rotation;
                e.Pointer.Capture(this);
                return;
            }

            foreach (var (handle, handlePos) in handles)
            {
                if (Distance(pos, handlePos) <= HandleHitRadius)
                {
                    BeginGesture(selected, DragMode.Resize, handle, pos);
                    e.Pointer.Capture(this);
                    return;
                }
            }
        }

        var hit = HitTest(pos);
        Owner?.SelectObject(hit);
        if (hit is not null)
        {
            BeginGesture(hit, DragMode.Move, default, pos);
            e.Pointer.Capture(this);
        }
    }

    protected override void OnPointerMoved(PointerEventArgs e)
    {
        base.OnPointerMoved(e);
        if (_mode == DragMode.None || _activeObject is null || Page is null || _lastPointerPos is not { } last) return;

        var pos = e.GetPosition(this);
        var model = _activeObject.Model;

        switch (_mode)
        {
            case DragMode.Move:
                model.X += (pos.X - last.X) / ScreenScale;
                model.Y -= (pos.Y - last.Y) / ScreenScale;
                break;

            case DragMode.Resize:
            {
                var worldDelta = new PointD((pos.X - last.X) / ScreenScale, -(pos.Y - last.Y) / ScreenScale);
                var lockAspect = e.KeyModifiers.HasFlag(KeyModifiers.Shift);
                var (x, y, w, h) = GeometryMath.ResizeObjectRect(
                    model.Center, model.Width, model.Height, model.Rotation, _activeHandle, worldDelta, minSize: 5.0, lockAspect);
                model.X = x; model.Y = y; model.Width = w; model.Height = h;
                break;
            }

            case DragMode.Rotate:
            {
                var currentAngle = AngleFromPivotDeg(_activeObject, pos);
                model.Rotation = _rotateStartRotationDeg + (currentAngle - _rotateStartAngleDeg);
                break;
            }
        }

        _activeObject.SyncFromModel(ScreenScale, Page.HeightPt);
        _lastPointerPos = pos;
        InvalidateVisual();
    }

    protected override void OnPointerReleased(PointerReleasedEventArgs e)
    {
        base.OnPointerReleased(e);
        if (_mode == DragMode.None) return;
        _mode = DragMode.None;
        _activeObject = null;
        _lastPointerPos = null;
        e.Pointer.Capture(null);
        Owner?.EndGesture();
        InvalidateVisual();
    }

    private void BeginGesture(ObjectViewModel obj, DragMode mode, ResizeHandle handle, Point pos)
    {
        _mode = mode;
        _activeObject = obj;
        _activeHandle = handle;
        _lastPointerPos = pos;
        Owner?.BeginGesture(obj);
    }

    private (IReadOnlyDictionary<ResizeHandle, Point> Handles, Point Rotate) GetHandlePositions(ObjectViewModel obj)
    {
        var page = Page!;
        Point ToScreen(PointD world) => new(world.X * ScreenScale, (page.HeightPt - world.Y) * ScreenScale);

        var pivot = obj.Model.Center;
        var local = GeometryMath.HandlePositions(obj.Model.Width, obj.Model.Height);
        var handles = local.ToDictionary(kv => kv.Key, kv => ToScreen(GeometryMath.LocalToWorld(kv.Value, pivot, obj.Model.Rotation)));

        var rotateLocal = new PointD(0, obj.Model.Height / 2.0 + RotateHandleOffsetPx / ScreenScale);
        var rotatePoint = ToScreen(GeometryMath.LocalToWorld(rotateLocal, pivot, obj.Model.Rotation));

        return (handles, rotatePoint);
    }

    private double AngleFromPivotDeg(ObjectViewModel obj, Point screenPos)
    {
        var page = Page!;
        var pivotWorld = obj.Model.Center;
        var pivotScreen = new Point(pivotWorld.X * ScreenScale, (page.HeightPt - pivotWorld.Y) * ScreenScale);
        return Math.Atan2(screenPos.Y - pivotScreen.Y, screenPos.X - pivotScreen.X) * 180.0 / Math.PI;
    }

    private static double Distance(Point a, Point b) => Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y));

    private ObjectViewModel? HitTest(Point screenPos)
    {
        var page = Page;
        var objects = Objects;
        if (page is null || objects is null) return null;
        var pdfX = screenPos.X / ScreenScale;
        var pdfY = page.HeightPt - screenPos.Y / ScreenScale;
        var worldPoint = new PointD(pdfX, pdfY);

        foreach (var obj in objects.OrderByDescending(o => o.Model.ZIndex))
        {
            var localRect = new RectD(-obj.Model.Width / 2, -obj.Model.Height / 2, obj.Model.Width, obj.Model.Height);
            if (GeometryMath.HitTestRotatedRect(worldPoint, localRect, obj.Model.Center, obj.Model.Rotation))
                return obj;
        }
        return null;
    }
}
