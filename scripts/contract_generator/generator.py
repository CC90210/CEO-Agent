import os
import io
import time
import smtplib
from email.message import EmailMessage
import mimetypes
import stripe
import argparse
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib import colors

# Load env vars
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env.agents'))

stripe.api_key = os.getenv("STRIPE_RESTRICTED_KEY") or os.getenv("STRIPE_SECRET_KEY")

class InvoiceContractGenerator:
    def __init__(self, output_dir="media/exports"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def generate_payment_link(self, product_name: str, upfront_amount: int, monthly_amount: int) -> str:
        """
        Generates a Stripe Payment Link for the specific service and amounts.
        """
        if not stripe.api_key:
            return "https://stripe.com/missing-key"
            
        try:
            # Create a simple ad-hoc product
            product = stripe.Product.create(name=product_name)
            
            line_items = []
            
            if upfront_amount > 0:
                upfront_price = stripe.Price.create(
                    product=product.id,
                    unit_amount=upfront_amount * 100,
                    currency="cad",
                )
                line_items.append({"price": upfront_price.id, "quantity": 1})
                
            if monthly_amount > 0:
                monthly_price = stripe.Price.create(
                    product=product.id,
                    unit_amount=monthly_amount * 100,
                    currency="cad",
                    recurring={"interval": "month"} 
                )
                line_items.append({"price": monthly_price.id, "quantity": 1})
                
            if not line_items:
                return "https://buy.stripe.com/error_no_amounts"
            
            # Create the payment link
            payment_link = stripe.PaymentLink.create(
                line_items=line_items
            )
            return payment_link.url
            
        except Exception as e:
            print(f"Stripe Error: {e}")
            return "https://buy.stripe.com/error"

    def generate_documents(self, client_name: str, client_email: str, upfront_amount: int, monthly_amount: int) -> tuple[str, str, str]:
        """
        Generates the PDF invoice and the PDF NDA/Contract.
        Returns the paths to the generated files, and the payment link.
        """
        timestamp = int(time.time())
        doc_prefix = client_name.lower().replace(" ", "_").replace("'", "")
        
        invoice_path = os.path.join(self.output_dir, f"{doc_prefix}_invoice_{timestamp}.pdf")
        contract_path = os.path.join(self.output_dir, f"{doc_prefix}_contract_{timestamp}.pdf")
        
        # 1. Generate Payment Link
        product_name = f"OASIS AI Service - {client_name}"
        payment_link = self.generate_payment_link(product_name, upfront_amount, monthly_amount)
        
        # 2. Generate PDF Invoice
        body_text_inv = [
            f"Billed To: {client_name}",
            f"Email: {client_email}",
            "\nService: Autonomous AI Management & Integration",
        ]
        if upfront_amount > 0:
            body_text_inv.append(f"Setup/Upfront Cost: ${upfront_amount}.00 CAD")
        if monthly_amount > 0:
            body_text_inv.append(f"Monthly Retainer: ${monthly_amount}.00 CAD")
            
        body_text_inv.extend([
            f"\nPlease pay via our secure portal: {payment_link}",
            "\nThank you for choosing OASIS AI Solutions."
        ])
        
        self._build_pdf(
            invoice_path, 
            title="OASIS AI Solutions - INVOICE",
            body_text=body_text_inv
        )
        
        # 3. Generate PDF Contract/NDA
        body_text_contract = [
            f"MASTER SERVICES AGREEMENT & NDA",
            f"This Master Service Agreement is entered into by OASIS AI Solutions ('Provider') and {client_name} ('Client').",
            "\nARTICLE 1. SERVICES PROVIDED",
            "Provider will deploy and maintain autonomous AI systems to streamline business operations.",
            "\nARTICLE 2. INTELLECTUAL PROPERTY & OWNERSHIP",
            "Provider retains all right, title, and interest in and to all Pre-Existing IP. Transfer of Project IP to Client is expressly conditioned upon full payment of all fees.",
            "This work is explicitly NOT a 'work made for hire' unless a separate signed agreement states otherwise.",
            "\nARTICLE 3. COMPENSATION & PAYMENT TERMS",
            f"Client agrees to the following compensation structure:"
        ]
        
        if upfront_amount > 0:
            body_text_contract.append(f"- One-time upfront setup fee: ${upfront_amount}.00 CAD (Non-refundable deposit)")
        if monthly_amount > 0:
            body_text_contract.append(f"- Monthly retainer fee: ${monthly_amount}.00 CAD")
            
        body_text_contract.extend([
            "\npayable via the secure portal linked below.",
            f"Payment Link: {payment_link}",
            "\nARTICLE 4. TERMINATION & BREACH",
            "Either party may terminate for convenience with 30 days notice. In such event, Client must pay for services to date plus a 25% termination fee of remaining estimated fees.",
            "Material breach by the client (like non-payment) immediately terminates all licenses and voids IP transfer provisions.",
            "\nARTICLE 5. NDA & CONFIDENTIALITY",
            "Provider will maintain strict confidentiality regarding all internal business processes, lead data, and financial information shared by the Client.",
            "\nARTICLE 6. LIABILITY CAP & GOVERNING LAW",
            "Total liability shall not exceed the total fees actually paid by Client to OASIS AI during the twelve months preceding the claim. This Agreement shall be governed by the laws of Ontario, Canada.",
            "\nSIGNATURES",
            "Payment of the above invoice acts as a digital signature and legally binding agreement to these terms.",
            "\n_________________________________________",
            "Conaugh McKenna, Founder | OASIS AI Solutions"
        ])
        
        self._build_pdf(
            contract_path,
            title="OASIS AI Solutions - MASTER AGREEMENT & NDA",
            body_text=body_text_contract
        )
        
        return invoice_path, contract_path, payment_link

    def _build_pdf(self, file_path: str, title: str, body_text: list):
        doc = SimpleDocTemplate(file_path, pagesize=letter)
        styles = getSampleStyleSheet()
        
        # Custom Title Style
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=30
        )
        
        body_style = styles['Normal']
        body_style.fontSize = 12
        body_style.leading = 18
        
        elements = []
        elements.append(Paragraph(title, title_style))
        
        for line in body_text:
            # basic clean up for reportlab XML quirks
            clean_line = line.replace("<", "&lt;").replace(">", "&gt;")
            if clean_line.startswith("\n"):
                elements.append(Spacer(1, 15))
                elements.append(Paragraph(clean_line.strip(), body_style))
            else:
                elements.append(Paragraph(clean_line, body_style))
                elements.append(Spacer(1, 10))
                
        doc.build(elements)

    def send_email_with_documents(self, client_name: str, client_email: str, invoice_path: str, contract_path: str, payment_link: str):
        gmail_user = os.environ.get("GMAIL_USER", "oasisaisolutions@gmail.com")
        gmail_pw = os.environ.get("GMAIL_APP_PASSWORD")
        
        if not gmail_pw:
            print("GMAIL_APP_PASSWORD not set. Cannot send email.")
            return

        msg = EmailMessage()
        msg['Subject'] = f"OASIS AI Solutions - Onboarding & Service Agreement for {client_name}"
        msg['From'] = gmail_user
        msg['To'] = client_email
        
        body = f"""Welcome to OASIS AI Solutions, {client_name}.

We are thrilled to officially partner with you to scale your operations through automation.

Attached to this email, you will find:
1. The Master Service Agreement & NDA
2. Your initial Invoice

To officially finalize your onboarding and activate our services, please review the attached forms and submit your payment via our secure portal here:
{payment_link}

(Note: Payment of the invoice acts as your digital signature on the Master Agreement).

If you have any questions, feel free to reply directly to this email.

Only good things,

Conaugh McKenna
Founder | OASIS AI Solutions
"""
        msg.set_content(body)
        
        # Attach Invoice
        with open(invoice_path, 'rb') as f:
            pdf_data = f.read()
            msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=os.path.basename(invoice_path))
            
        # Attach Contract
        with open(contract_path, 'rb') as f:
            pdf_data = f.read()
            msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=os.path.basename(contract_path))

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(gmail_user, gmail_pw)
                smtp.send_message(msg)
            print(f"✅ Onboarding email sent to {client_email}")
        except Exception as e:
            print(f"❌ Failed to send email: {e}")

def onboard_client(client_name: str, client_email: str, upfront_amount: int, monthly_amount: int):
    print(f"Starting onboarding for {client_name} ({client_email})...")
    gen = InvoiceContractGenerator()
    
    print("Generating Stripe Link and PDF Documents...")
    inv_path, con_path, pmt_link = gen.generate_documents(client_name, client_email, upfront_amount, monthly_amount)
    print(f"- Invoice saved to: {inv_path}")
    print(f"- Contract saved to: {con_path}")
    print(f"- Payment Link: {pmt_link}")
    
    print("Dispatching final onboarding email...")
    gen.send_email_with_documents(client_name, client_email, inv_path, con_path, pmt_link)
    print("Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OASIS AI Client Onboarding Generator")
    parser.add_argument("--name", required=True, help="Client's Name or Company Name")
    parser.add_argument("--email", required=True, help="Client's Email Address")
    parser.add_argument("--upfront", type=int, required=True, help="Upfront Setup Fee (CAD)")
    parser.add_argument("--monthly", type=int, required=True, help="Monthly Retainer Fee (CAD)")
    
    args = parser.parse_args()
    
    onboard_client(
        client_name=args.name,
        client_email=args.email,
        upfront_amount=args.upfront,
        monthly_amount=args.monthly
    )
