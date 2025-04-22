from .support._reader import PdfReader
from .support._writer import PdfWriter

def split_pdf_into_single_pages(input_pdf):
    with open(input_pdf, 'rb') as f:
        pdf = PdfReader(f)
        num_pages = len(pdf.pages)
        for i in range(num_pages):
            writer = PdfWriter()
            writer.add_page(pdf.pages[i])
            with open(f'page_{i+1}.pdf', 'wb') as outf:
                writer.write(outf)

def split_pdf_into_multiple_files(input_pdf, pages_per_file):
    with open(input_pdf, 'rb') as f:
        pdf = PdfReader(f)
        num_pages = len(pdf.pages)
        num_files = -(-num_pages // pages_per_file)
        for i in range(num_files):
            writer = PdfWriter()
            for j in range(pages_per_file):
                page_num = i * pages_per_file + j
                if page_num < num_pages:
                    writer.add_page(pdf.pages[page_num])
            with open(f'output_{i+1}.pdf', 'wb') as outf:
                writer.write(outf)

def extract_between_pages(input_pdf, start_page, end_page):
    with open(input_pdf, 'rb') as f:
        pdf = PdfReader(f)
        writer = PdfWriter()

        for i in range(start_page-1, end_page):
            writer.add_page(pdf.pages[i])

        with open('output.pdf', 'wb') as outf:
            writer.write(outf)