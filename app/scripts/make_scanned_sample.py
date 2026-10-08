import pymupdf

src = pymupdf.open()
page = src.new_page()
page.insert_text((72, 100), "Scanned leave policy: employees receive 20 days annual leave.",
                 fontsize=14)
pix = page.get_pixmap(dpi=200)

out = pymupdf.open()
new = out.new_page(width=page.rect.width, height=page.rect.height)
new.insert_image(new.rect, pixmap=pix)
out.save("/code/scanned.pdf")
print("Created scanned.pdf (image only, no text layer)")