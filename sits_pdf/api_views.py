import base64
import io
import os
import uuid
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import default_storage
from django.conf import settings
from .serializers import PDFFileSerializer
from .merger import PdfMerger
from .views import compress_pdf_in_memory
from .views import convert_pdf_to_docx
from .views import extract_tables_and_content
from .views import write_to_excel
from .pdf_to_image_covert import convert_from_bytes
import zipfile
from PIL import Image
import tempfile
from .support._reader import PdfReader
from .support._writer import PdfWriter
from io import BytesIO
from playwright.sync_api import sync_playwright
from django.http import HttpResponse

class MergePDFAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, format=None):
        files = request.FILES.getlist('files')
        if not files:
            return Response({"error": "No files were submitted."}, status=status.HTTP_400_BAD_REQUEST)

        file_data = []
        for file in files:
            if not file.name.lower().endswith('.pdf'):
                return Response({"error": f"{file.name} is not a PDF file."}, status=status.HTTP_400_BAD_REQUEST)

            serializer = PDFFileSerializer(data={'file': file})
            if serializer.is_valid():
                file_data.append({
                    "filename": file.name,
                    "content": base64.b64encode(file.read()).decode('utf-8')
                })
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            merger = PdfMerger()
            for pdf in file_data:
                pdf_bytes = base64.b64decode(pdf['content'])
                pdf_io = io.BytesIO(pdf_bytes)
                merger.append(pdf_io)

            output = io.BytesIO()
            merger.write(output)
            output.seek(0)
            merged_content = output.getvalue()

            # Return the merged PDF file directly
            response = HttpResponse(merged_content, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="merged.pdf"'
            return response

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            merger.close()

    def get(self, request, format=None):
        return Response({
            "message": "This endpoint merges multiple PDF files.",
            "instructions": "Send a POST request with 'files' as the key and multiple PDF files as the value."
        })
    
class SplitPDFAPI(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, format=None):
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file was submitted."}, status=status.HTTP_400_BAD_REQUEST)

        if not file.name.lower().endswith('.pdf'):
            return Response({"error": f"{file.name} is not a PDF file."}, status=status.HTTP_400_BAD_REQUEST)

        pdf_bytes = file.read()

        try:
            with BytesIO(pdf_bytes) as f:
                pdf = PdfReader(f)
                num_pages = len(pdf.pages)

                split_type = request.POST.get("split_type")

                if split_type == "custom":
                    start_page = int(request.POST.get("start_page"))
                    end_page = int(request.POST.get("end_page"))
                    writer = PdfWriter()
                    for i in range(start_page - 1, end_page):
                        writer.add_page(pdf.pages[i])
                    output_pdf = BytesIO()
                    writer.write(output_pdf)
                    output_pdf.seek(0)
                    output_data = output_pdf.getvalue()
                    output_filename = f"extracted_pages_{start_page}_{end_page}.pdf"
                    output_type = "application/pdf"

                elif split_type == "fixed_range":
                    pages_per_file = int(request.POST.get("pages_per_file"))
                    num_files = -(-num_pages // pages_per_file)
                    pdf_files = []
                    for i in range(num_files):
                        writer = PdfWriter()
                        for j in range(pages_per_file):
                            page_num = i * pages_per_file + j
                            if page_num < num_pages:
                                writer.add_page(pdf.pages[page_num])
                        output_pdf = BytesIO()
                        writer.write(output_pdf)
                        output_pdf.seek(0)
                        pdf_files.append(output_pdf.getvalue())

                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                        for i, pdf_file in enumerate(pdf_files):
                            zip_file.writestr(
                                f"{os.path.splitext(file.name)[0]}_part_{i+1}.pdf",
                                pdf_file,
                            )
                    zip_buffer.seek(0)
                    output_data = zip_buffer.getvalue()
                    output_filename = f"split_files_{file.name}.zip"
                    output_type = "application/zip"

                elif split_type == "all_pages":
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                        for i in range(num_pages):
                            writer = PdfWriter()
                            writer.add_page(pdf.pages[i])
                            pdf_data = BytesIO()
                            writer.write(pdf_data)
                            pdf_data.seek(0)
                            zip_file.writestr(f"page_{i+1}.pdf", pdf_data.getvalue())
                    zip_buffer.seek(0)
                    output_data = zip_buffer.getvalue()
                    output_filename = "single_pages.zip"
                    output_type = "application/zip"

                elif split_type == "selected_pages":
                    pages_to_extract = request.POST.get("pages_to_extract")
                    writer = PdfWriter()
                    pages_to_extract_list = []
                    for page_range in pages_to_extract.split(","):
                        page_range = page_range.strip()
                        if "-" in page_range:
                            start, end = map(int, page_range.split("-"))
                            pages_to_extract_list.extend(range(start, end + 1))
                        else:
                            pages_to_extract_list.append(int(page_range))
                    for page_num in pages_to_extract_list:
                        if 1 <= page_num <= num_pages:
                            writer.add_page(pdf.pages[page_num - 1])
                        else:
                            return Response({"error": f"Error splitting PDF : Invalid page number "}, status=status.HTTP_400_BAD_REQUEST)
                    output_pdf = BytesIO()
                    writer.write(output_pdf)
                    output_pdf.seek(0)
                    output_data = output_pdf.getvalue()
                    output_filename = "extracted_pages.pdf"
                    output_type = "application/pdf"

                else:
                    return Response({"error": "Invalid split type"}, status=status.HTTP_400_BAD_REQUEST)

            # Return the split PDF file directly
            response = HttpResponse(output_data, content_type=output_type)
            response['Content-Disposition'] = f'attachment; filename="{output_filename}"'
            return response

        except Exception as e:
            return Response({"error": "Failed to split PDF."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request, format=None):
        return Response({
            "message": "This endpoint splits a PDF file.",
            "instructions": "Send a POST request with 'file' as the key and a PDF file as the value."
        })
    
class CompressPDFAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, format=None):
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file was submitted."}, status=status.HTTP_400_BAD_REQUEST)

        if not file.name.lower().endswith('.pdf'):
            return Response({"error": f"{file.name} is not a PDF file."}, status=status.HTTP_400_BAD_REQUEST)

        pdf_bytes = file.read()

        try:
            compressed_pdf_bytes = compress_pdf_in_memory(pdf_bytes, quality='ebook')
        except Exception as e:
            return Response({"error": "Failed to compress PDF."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Return the compressed PDF file directly
        response = HttpResponse(compressed_pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="compressed.pdf"'
        return response

    def get(self, request, format=None):
        return Response({
            "message": "This endpoint compresses a single PDF file.",
            "instructions": "Send a POST request with 'file' as the key and a PDF file as the value."
        })
    
class PDFToWordAPI(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, format=None):
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file was submitted."}, status=status.HTTP_400_BAD_REQUEST)

        if not file.name.lower().endswith('.pdf'):
            return Response({"error": f"{file.name} is not a PDF file."}, status=status.HTTP_400_BAD_REQUEST)

        pdf_bytes = file.read()

        try:
            docx_bytes = convert_pdf_to_docx(pdf_bytes)
        except Exception as e:
            return Response({"error": "Failed to convert PDF to Word."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Return the converted Word file directly
        response = HttpResponse(docx_bytes, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        response['Content-Disposition'] = f'attachment; filename="{file.name.replace(".pdf", ".docx")}"'
        return response

    def get(self, request, format=None):
        return Response({
            "message": "This endpoint converts a PDF file to a Word document.",
            "instructions": "Send a POST request with 'file' as the key and a PDF file as the value."
        })
    
class PDFToJPGAPI(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, format=None):
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file was submitted."}, status=status.HTTP_400_BAD_REQUEST)

        if not file.name.lower().endswith('.pdf'):
            return Response({"error": f"{file.name} is not a PDF file."}, status=status.HTTP_400_BAD_REQUEST)

        pdf_bytes = file.read()

        try:
            images = convert_from_bytes(pdf_bytes)
            num_images = len(images)

            if num_images == 1:
                # Single page PDF
                image_io = io.BytesIO()
                images[0].save(image_io, format="JPEG", quality=95)
                image_io.seek(0)

                jpg_bytes = image_io.getvalue()
                jpg_filename = f"{file.name.replace('.pdf', '.jpg')}"

                # Return the converted JPG file directly
                response = HttpResponse(jpg_bytes, content_type='image/jpeg')
                response['Content-Disposition'] = f'attachment; filename="{jpg_filename}"'
                return response
            else:
                # Multi-page PDF
                zip_io = io.BytesIO()
                with zipfile.ZipFile(zip_io, "w") as zip_file:
                    for i, image in enumerate(images):
                        image_io = io.BytesIO()
                        image.save(image_io, format="JPEG", quality=95)
                        image_io.seek(0)
                        zip_file.writestr(f"page_{i+1}.jpg", image_io.getvalue())

                zip_io.seek(0)
                zip_bytes = zip_io.getvalue()
                zip_filename = f"{file.name.replace('.pdf', '.zip')}"

                # Return the converted ZIP file directly
                response = HttpResponse(zip_bytes, content_type='application/zip')
                response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
                return response
        except Exception as e:
            return Response({"error": "Failed to convert PDF to JPG."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request, format=None):
        return Response({
            "message": "This endpoint converts a PDF file to JPG images.",
            "instructions": "Send a POST request with 'file' as the key and a PDF file as the value."
        })
    
class JPGToPDFAPI(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, format=None):
        files = request.FILES.getlist('files')
        if not files:
            return Response({"error": "No files were submitted."}, status=status.HTTP_400_BAD_REQUEST)

        images = []
        for file in files:
            if not file.name.lower().endswith('.jpg') and not file.name.lower().endswith('.jpeg'):
                return Response({"error": f"{file.name} is not a JPG file."}, status=status.HTTP_400_BAD_REQUEST)

            image_data = file.read()
            image_io = io.BytesIO(image_data)
            image = Image.open(image_io)
            images.append(image)

        try:
            pdf_io = io.BytesIO()
            images[0].save(
                pdf_io, format="PDF", save_all=True, append_images=images[1:]
            )
            pdf_io.seek(0)

            pdf_bytes = pdf_io.getvalue()
            pdf_filename = "converted.pdf"

            # Return the converted PDF file directly
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{pdf_filename}"'
            return response

        except Exception as e:
            return Response({"error": "Failed to convert JPG images to PDF."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request, format=None):
        return Response({
            "message": "This endpoint converts JPG images to a PDF file.",
            "instructions": "Send a POST request with 'files' as the key and JPG files as the values."
        })
    
class ConvertURLToPDFView(APIView):
    def post(self, request, format=None):
        url_to_fetch = request.POST.get("url")

        paper_format = request.POST.get("paper_format")

        margin = request.POST.get("margin")

        landscape_allow = request.POST.get("landscape_allow")
        if landscape_allow and landscape_allow.lower() == "true":
            landscape_allow_bool = True
        else:
            landscape_allow_bool = False

        landscape_allow_bool = landscape_allow and landscape_allow.lower() == "true"

        if margin == "none":
            top_margin = 0
            bottom_margin = 0
            left_margin = 0
            right_margin = 0
        elif margin == "small":
            top_margin = 0.5
            bottom_margin = 0.5
            left_margin = 0.5
            right_margin = 0.5
        elif margin == "large":
            top_margin = 1
            bottom_margin = 1
            left_margin = 1
            right_margin = 1

        if url_to_fetch and paper_format:
            try:
                with sync_playwright() as p:
                    browser_type = p.chromium
                    browser = browser_type.launch(headless=True)
                    context = browser.new_context()
                    page = context.new_page()
                    page.goto(url_to_fetch)
                    page.wait_for_load_state("networkidle")

                    pdf = page.pdf(
                        format=paper_format,
                        print_background=True,
                        margin={
                            "top": f"{top_margin}cm",
                            "bottom": f"{bottom_margin}cm",
                            "left": f"{left_margin}cm",
                            "right": f"{right_margin}cm",
                        },
                        landscape = landscape_allow_bool,
                    )

                # Return the converted PDF file directly
                response = HttpResponse(pdf, content_type="application/pdf")
                response['Content-Disposition'] = 'attachment; filename="converted.pdf"'
                return response

            except Exception as e:
                return Response({"error": f"Error processing files: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        else:
            return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

    def get(self, request, format=None):
        return Response({
            "message": "This endpoint converts a URL to a PDF file.",
            "instructions": "Send a POST request with 'url' and 'paper_format' as keys."
        })
    
class PDFTOExcelAPI(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, format=None):
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file was submitted."}, status=status.HTTP_400_BAD_REQUEST)

        if not file.name.lower().endswith('.pdf'):
            return Response({"error": f"{file.name} is not a PDF file."}, status=status.HTTP_400_BAD_REQUEST)

        pdf_bytes = file.read()

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                temp_pdf.write(pdf_bytes)
                temp_pdf_path = temp_pdf.name

                tables, image_list, text_content = extract_tables_and_content(temp_pdf_path)
                excel_bytes = write_to_excel(tables, image_list, text_content)

            os.unlink(temp_pdf_path)

            excel_filename = f"converted_{uuid.uuid4()}.xlsx"

            # Return the converted Excel file directly
            response = HttpResponse(excel_bytes, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="{excel_filename}"'
            return response

        except Exception as e:
            return Response({"error": "Failed to convert PDF to Excel."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request, format=None):
        return Response({
            "message": "This endpoint converts a PDF file to an Excel spreadsheet.",
            "instructions": "Send a POST request with 'file' as the key and a PDF file as the value."
        })
    
