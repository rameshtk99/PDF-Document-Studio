using System.Collections.Concurrent;
using System.Threading;
using PDFDocumentStudio.Pdf.Rendering;
using SkiaSharp;

namespace PDFDocumentStudio.Rendering.Caching;

public readonly record struct PageBitmapReadyArgs(string SourcePath, int PageIndex, double Dpi);

/// <summary>
/// LRU cache of rendered page bitmaps, keyed by (source file, page, DPI). Rendering happens on a
/// background task and never blocks the caller; <see cref="Ready"/> fires when a requested bitmap
/// becomes available so the UI can redraw. Bounded to <paramref name="maxCachedPages"/> entries —
/// page-level granularity rather than sub-page tiles (see PERFORMANCE.md for why).
/// </summary>
public sealed class PageBitmapCache(PdfPageRasterRenderer renderer, int maxCachedPages = 32) : IDisposable
{
    private readonly Lock _lock = new();
    private readonly LinkedList<string> _lruOrder = new();
    private readonly Dictionary<string, LinkedListNode<string>> _lruNodes = new();
    private readonly Dictionary<string, SKBitmap> _bitmaps = new();
    private readonly ConcurrentDictionary<string, byte> _pending = new();
    private readonly SemaphoreSlim _concurrency = new(Environment.ProcessorCount is var n && n > 2 ? n / 2 : 1);

    public event Action<PageBitmapReadyArgs>? Ready;

    /// <summary>Fires when a background render throws — rendering degrades to "stays unrendered"
    /// rather than crashing, but a silent failure here previously meant a page could sit blank
    /// forever with no visible cause; surface it so the UI can report what actually happened.</summary>
    public event Action<string, Exception>? RenderFailed;

    public SKBitmap? TryGet(string sourcePath, int pageIndex, double dpi)
    {
        var key = Key(sourcePath, pageIndex, dpi);
        lock (_lock)
        {
            if (!_bitmaps.TryGetValue(key, out var bitmap)) return null;
            Touch(key);
            return bitmap;
        }
    }

    /// <summary>Fires a background render if the bitmap isn't already cached or in flight. Safe to
    /// call repeatedly (e.g. once per frame while scrolling) — duplicate requests are no-ops.</summary>
    public void RequestAsync(string sourcePath, int pageIndex, double dpi)
    {
        var key = Key(sourcePath, pageIndex, dpi);
        lock (_lock) { if (_bitmaps.ContainsKey(key)) return; }
        if (!_pending.TryAdd(key, 0)) return;

        _ = Task.Run(async () =>
        {
            await _concurrency.WaitAsync();
            try
            {
                var bitmap = renderer.RenderPage(sourcePath, pageIndex, dpi);
                Store(key, bitmap);
                Ready?.Invoke(new PageBitmapReadyArgs(sourcePath, pageIndex, dpi));
            }
            catch (Exception ex)
            {
                // Rendering failures degrade to "stays unrendered" — the caller's placeholder stays up.
                RenderFailed?.Invoke(sourcePath, ex);
            }
            finally
            {
                _concurrency.Release();
                _pending.TryRemove(key, out _);
            }
        });
    }

    /// <summary>Drops every cached bitmap for a page's current zoom that ISN'T in
    /// <paramref name="keepDpis"/> — call when zoom changes to free stale-resolution bitmaps.</summary>
    public void EvictExcept(string sourcePath, int pageIndex, IReadOnlyCollection<double> keepDpis)
    {
        lock (_lock)
        {
            var prefix = $"{sourcePath}|{pageIndex}|";
            foreach (var key in _bitmaps.Keys.Where(k => k.StartsWith(prefix, StringComparison.Ordinal)).ToList())
            {
                var dpi = double.Parse(key.AsSpan(prefix.Length));
                if (!keepDpis.Contains(dpi)) Remove(key);
            }
        }
    }

    private void Store(string key, SKBitmap bitmap)
    {
        lock (_lock)
        {
            if (_bitmaps.TryGetValue(key, out var old)) old.Dispose();
            _bitmaps[key] = bitmap;
            Touch(key);
            while (_bitmaps.Count > maxCachedPages && _lruOrder.Last is { } lru)
            {
                Remove(lru.Value);
            }
        }
    }

    private void Touch(string key)
    {
        if (_lruNodes.TryGetValue(key, out var node)) _lruOrder.Remove(node);
        _lruNodes[key] = _lruOrder.AddFirst(key);
    }

    private void Remove(string key)
    {
        if (_bitmaps.Remove(key, out var bitmap)) bitmap.Dispose();
        if (_lruNodes.Remove(key, out var node)) _lruOrder.Remove(node);
    }

    private static string Key(string sourcePath, int pageIndex, double dpi) => $"{sourcePath}|{pageIndex}|{dpi}";

    public void Dispose()
    {
        lock (_lock)
        {
            foreach (var bitmap in _bitmaps.Values) bitmap.Dispose();
            _bitmaps.Clear();
            _lruOrder.Clear();
            _lruNodes.Clear();
        }
        _concurrency.Dispose();
    }
}
