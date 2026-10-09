# Import reference fixture

`formulas.xls` is a BIFF8 workbook generated with xlwt 1.3.0: two sheets,
a `B1*60` formula without a cached result and merged cells. No athlete data or macros.
Tests also generate real XLSX/PDF/PNG bytes in isolated temporary storage. Browser
fixtures render printed French instructions into tilted images and three-page PDFs
(textual, scanned and mixed) before invoking the application's actual extraction.
