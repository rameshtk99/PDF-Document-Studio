namespace PDFDocumentStudio.Tests.Pdf;

[Collection("Pdf")]
public class WhiteSpaceDetectorTests(PdfTestFixture fixture)
{
    [Fact]
    public void AnalyzeContentBottomFraction_RealPage_ReturnsValueInValidRange()
    {
        var fraction = fixture.WhiteSpace.AnalyzeContentBottomFraction(fixture.SamplePdfPath, 0);
        Assert.InRange(fraction, 0.0, 1.0);
    }
}
