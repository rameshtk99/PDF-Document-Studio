using System.Globalization;
using Avalonia.Data.Converters;
using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.App.Services;

/// <summary>Binds a <see cref="FooterCellAlign"/> to/from a ComboBox's 0-based SelectedIndex
/// (Left, Center, Right in that order).</summary>
public sealed class AlignToIndexConverter : IValueConverter
{
    public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        value is FooterCellAlign align ? (int)align : 1;

    public object? ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        value is int index && index is >= 0 and <= 2 ? (FooterCellAlign)index : FooterCellAlign.Center;
}
