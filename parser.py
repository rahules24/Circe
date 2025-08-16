import re
import json
import os
import logging
import pdfplumber
import PyPDF2
from datetime import datetime

logger = logging.getLogger(__name__)

# --- COMPREHENSIVE BANK PATTERNS DATABASE ---
# Consolidated from analyze_pdf.py, parser.py, and enhanced with additional robustness
COMPREHENSIVE_BANK_PATTERNS = {
    'sbi': {
        'card_number': [
            r'XXXX XXXX XXXX (\w+)',
            r'XXXX XXXX XXXX (\w{2,4})',
            r'Credit Card Number.*?XXXX XXXX XXXX (\w+)',
            r'XXXX\s+XXXX\s+XXXX\s+XX(\d{2,4})'
        ],
        'statement_date': [
            r'Statement\s*Date\s*[:\-]?\s*(\d{2}\s+[A-Za-z]{3}\s+\d{4})',
            r'Statement\s*Date\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
            r'Statement.*?Date.*?(\d{2}/\d{2}/\d{4})',
            r'Statement.*?(\d{2}-\d{2}-\d{4})'
        ],
        'total_due': [
            r'Total Payment Due\s*[:\-]?\s*₹?\s*([\d,]+\.\d{2})',
            r'Total Amount Due\s*[:\-]?\s*₹?\s*([\d,]+\.\d{2})',
            r'\*Total Amount Due.*?([\d,]+\.\d{2})'
        ],
        'due_date': [
            # Label on one line, date on next line or far right
            r'Payment\s+Due\s+Date[\s:\-.]*?(?:\r?\n|\s)+.*?([0-3]?\d\s+[A-Za-z]{3}\s+\d{4})',
            r'Payment\s+Due\s+Date[\s:\-.]*?(?:\r?\n|\s)+.*?(\d{2}/\d{2}/\d{4})',
            r'Payment\s+Due\s+Date[\s:\-.]*?(?:\r?\n|\s)+.*?(\d{2}-[A-Za-z]{3}-\d{4})',
            # Same-line variants
            r'(?:Total\s+)?Payment\s+Due\s+Date\s*[:\-]?\s*([0-3]?\d\s+[A-Za-z]{3}\s+\d{4})',
            r'Payment\s+Due\s+Date\s*[:\-]?\s*(\d{2}-[A-Za-z]{3}-\d{4})',
            r'Payment\s+Due\s+Date\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})'
        ],
        'min_due': [
            r'Minimum\s+(?:Amount|Payment)\s+Due\s*[:\-]?\s*₹?\s*([\d,]+\.\d{2})',
            r'\*\*Minimum Amount Due.*?([\d,]+\.\d{2})'
        ],
        'credit_limit': [
            r'Credit\s+Limit\s*\(.*?\)\s*[:\-]?\s*₹?\s*([\d,]+\.\d{2})',
            r'Credit\s+Limit.*?₹?\s*([\d,]+\.\d{2})'
        ],
        'available_limit': [
            r'Available\s+Credit\s+Limit\s*[:\-]?\s*₹?\s*([\d,]+\.\d{2})',
            r'Available.*?Limit.*?₹?\s*([\d,]+\.\d{2})'
        ]
    },
    'indusind': {
        'card_number': [
            r'Credit Card No\. (\d{4})XXXXXXXX(\d{4})',
            r'Credit Card No\.\s+\d{4}X+(\d{4})',
            r'Card.*?No.*?(\d{4})XXXXXXXX(\d{4})',
            r'(\d{4})\*+(\d{4})'
        ],
        'statement_date': [
            r'Statement Date\s+(\d{2}/\d{2}/\d{4})',
            r'Statement.*?Date.*?(\d{2}/\d{2}/\d{4})',
            r'Statement.*?(\d{2}-\d{2}-\d{4})'
        ],
        'total_due': [
            r'Total Amount Due[\s\S]*?([\d,]+\.\d{2}) DR',
            r'Total Amount Due\s+([\d,]+\.\d{2})\s+DR',
            r'Total.*?Due.*?([\d,]+\.\d{2})',
            r'Amount Due.*?([\d,]+\.\d{2})'
        ],
        'due_date': [
            r'Payment Due Date\s+(\d{2}/\d{2}/\d{4})',
            r'Due Date.*?(\d{2}/\d{2}/\d{4})',
            r'Pay.*?by.*?(\d{2}/\d{2}/\d{4})'
        ],
        'min_due': [
            r'Minimum Amount Due\s+([\d,]+\.\d{2})',
            r'Min.*?Due.*?([\d,]+\.\d{2})',
            r'MAD.*?([\d,]+\.\d{2})'
        ],
        'credit_limit': [
            r'Credit.*?Credit Limit\s+([\d,]+\.\d{2})',
            r'Total.*?Limit.*?([\d,]+\.\d{2})',
            r'Credit Limit.*?([\d,]+\.\d{2})'
        ],
        'available_limit': [
            r'Available Credit Limit\s+([\d,]+\.\d{2})',
            r'Available.*?Limit.*?([\d,]+\.\d{2})'
        ]
    },
    'axis': {
        'card_number': [
            r'(\d{6})\*+(\d{4})',
            r'(\d{4})\*+(\d{4})',
            r'Card.*?(\d{6})\*+(\d{4})',
            r'Neo.*?(\d{6})\*+(\d{4})'
        ],
        'statement_date': [
            r'Statement\s*Date\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})',
            r'Generation\s*Date\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})'
        ],
        'total_due': [
            r'([\d,]+\.\d{2}) Dr\s+([\d,]+\.\d{2}) Dr',
            r'Total Payment Due.*?([\d,]+\.\d{2})',
            r'Total.*?Due.*?([\d,]+\.\d{2}) Dr',
            r'Amount Due.*?([\d,]+\.\d{2})'
        ],
        'due_date': [
            r'(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s*$',
            r'Payment Due Date.*?(\d{2}/\d{2}/\d{4})',
            r'Due.*?(\d{2}/\d{2}/\d{4})'
        ],
        'min_due': [
            r'([\d,]+\.\d{2}) Dr\s+([\d,]+\.\d{2}) Dr',
            r'Minimum Payment Due.*?([\d,]+\.\d{2})',
            r'Min.*?Due.*?([\d,]+\.\d{2})'
        ],
        'credit_limit': [
            r'Credit Limit\s+([\d,]+\.\d{2})',
            r'Total.*?Limit.*?([\d,]+\.\d{2})'
        ],
        'available_limit': [
            r'Available Credit Limit\s+([\d,]+\.\d{2})',
            r'Available.*?Limit.*?([\d,]+\.\d{2})'
        ]
    },
    'icici': {
        'card_number': [
            r'(\d{4})XXXXXXXX(\d{4})',
            r'(\d{4})\*+(\d{4})',
            r'Card.*?(\d{4})XXXXXXXX(\d{4})',
            r'Credit Card.*?(\d{4})\*+(\d{4})'
        ],
        'statement_date': [
            r'SSTTAATTEEMMEENNTT DDAATTEE\s+(\w+ \d{1,2}, \d{4})',
            r'Statement.*?Date.*?(\w+ \d{1,2}, \d{4})',
            r'Statement.*?(\d{2}/\d{2}/\d{4})',
            r'STATEMENT.*?(\d{2}/\d{2}/\d{4})'
        ],
        'total_due': [
            r'Total Amount due\s+-\s+`([\d,]+\.\d{2})',
            r'Total.*?due.*?`([\d,]+\.\d{2})',
            r'Total Amount.*?([\d,]+\.\d{2})',
            r'Amount due.*?([\d,]+\.\d{2})',
            r'TOTAL\s+([\d,]+\.\d{2})'
        ],
        'due_date': [
            r'PPAAYYMMEENNTT DDUUEE DDAATTEE\s+(\w+ \d{1,2}, \d{4})',
            r'Payment.*?Due.*?Date.*?(\w+ \d{1,2}, \d{4})',
            r'Due Date.*?(\d{2}/\d{2}/\d{4})',
            r'PAYMENT.*?DUE.*?(\d{2}/\d{2}/\d{4})'
        ],
        'min_due': [
            r'Minimum Amount due.*?`([\d,]+\.\d{2})',
            r'Minimum.*?due.*?([\d,]+\.\d{2})',
            r'Min.*?Amount.*?([\d,]+\.\d{2})'
        ],
        'credit_limit': [
            r'Credit Limit \(Including cash\).*?`([\d,]+\.\d{2})',
            r'Credit Limit.*?`([\d,]+\.\d{2})',
            r'Total.*?Limit.*?([\d,]+\.\d{2})'
        ],
        'available_limit': [
            r'Available Credit \(Including cash\).*?`([\d,]+\.\d{2})',
            r'Available.*?Credit.*?`([\d,]+\.\d{2})',
            r'Available.*?([\d,]+\.\d{2})'
        ]
    },
    'kotak': {
        'card_number': [
            r'(\d{4})XXXXXXXX(\d{4})',
            r'(\d{4})\*+(\d{4})',
            r'Card.*?(\d{4})XXXXXXXX(\d{4})'
        ],
        'statement_date': [
            r'Statement Date (\d{2}-\w{3}-\d{4})',
            r'Statement.*?Date.*?(\d{2}-\w{3}-\d{4})',
            r'Statement.*?(\d{2}/\d{2}/\d{4})'
        ],
        'total_due': [
            r'Total Amount Due \(TAD\) Rs\.([\d,]+\.\d{2})',
            r'Total.*?Due.*?Rs\.([\d,]+\.\d{2})',
            r'TAD.*?Rs\.([\d,]+\.\d{2})',
            r'Amount Due.*?([\d,]+\.\d{2})'
        ],
        'due_date': [
            r'Remember to pay by (\d{2}-\w{3}-\d{4})',
            r'Pay by (\d{2}-\w{3}-\d{4})',
            r'Due.*?(\d{2}-\w{3}-\d{4})',
            r'Payment.*?(\d{2}/\d{2}/\d{4})'
        ],
        'min_due': [
            r'Minimum Amount Due \(MAD\) Rs\.([\d,]+\.\d{2})',
            r'MAD.*?Rs\.([\d,]+\.\d{2})',
            r'Minimum.*?Rs\.([\d,]+\.\d{2})'
        ],
        'credit_limit': [
            r'Total Credit Limit \(incl\.cash\): Rs\.([\d,]+\.\d{2})',
            r'Credit Limit.*?Rs\.([\d,]+\.\d{2})',
            r'Total.*?Limit.*?Rs\.([\d,]+\.\d{2})'
        ],
        'available_limit': [
            r'Available Credit Limit: Rs\.([\d,]+\.\d{2})',
            r'Available.*?Rs\.([\d,]+\.\d{2})',
            r'Available.*?Limit.*?([\d,]+\.\d{2})'
        ]
    },
    'rbl': {
        'card_number': [
            r'XXXXXXXXXXXXXX(\d{2})',
            r'(\d{4})\*+(\d{4})',
            r'Card.*?(\d{4})\*+(\d{4})',
            r'XXXX.*?(\d{4})'
        ],
        'statement_date': [
            r'Statement Date\s+(\d{2}-\d{2}-\d{4})',
            r'Statement.*?Date.*?(\d{2}-\d{2}-\d{4})',
            r'Statement.*?(\d{2}/\d{2}/\d{4})'
        ],
        'total_due': [
            r'Total Amount Due\s+([\d,]+\.\d{2})',
            r'Total.*?Due.*?([\d,]+\.\d{2})',
            r'Amount Due.*?([\d,]+\.\d{2})'
        ],
        'due_date': [
            r'Payment Due Date\s+(\d{2} \w{3} \d{4})',
            r'Due Date.*?(\d{2} \w{3} \d{4})',
            r'Payment.*?(\d{2}/\d{2}/\d{4})'
        ],
        'min_due': [
            r'Min\. Amt\. Due\s+([\d,]+\.\d{2})',
            r'Minimum.*?Due.*?([\d,]+\.\d{2})',
            r'Min.*?Due.*?([\d,]+\.\d{2})'
        ],
        'credit_limit': [
            r'Total Credit Limit\s+([\d,]+\.\d{2})',
            r'Credit Limit.*?([\d,]+\.\d{2})',
            r'Total.*?Limit.*?([\d,]+\.\d{2})'
        ],
        'available_limit': [
            r'Available Credit Limit\s+([\d,]+\.\d{2})',
            r'Available.*?Limit.*?([\d,]+\.\d{2})'
        ]
    },
    'hdfc': {
        'card_number': [
            r'(\d{4})\s*\*+\s*(\d{4})',
            r'(\d{4})XXXXXXXX(\d{4})',
            r'Card.*?(\d{4})\*+(\d{4})',
            r'HDFC.*?(\d{4})\*+(\d{4})'
        ],
        'statement_date': [
            r'Statement Date\s*:?\s*(\d{2}/\d{2}/\d{4})',
            r'Statement.*?(\d{2}-\d{2}-\d{4})',
            r'Date.*?(\d{2}/\d{2}/\d{4})'
        ],
        'total_due': [
            r'Total Amount Due\s*:?\s*Rs\.?\s*([\d,]+\.\d{2})',
            r'Total.*?Due.*?Rs\.?\s*([\d,]+\.\d{2})',
            r'Amount Due.*?([\d,]+\.\d{2})'
        ],
        'due_date': [
            r'Payment Due Date\s*:?\s*(\d{2}/\d{2}/\d{4})',
            r'Due Date.*?(\d{2}/\d{2}/\d{4})',
            r'Pay.*?by.*?(\d{2}/\d{2}/\d{4})'
        ],
        'min_due': [
            r'Minimum Amount Due\s*:?\s*Rs\.?\s*([\d,]+\.\d{2})',
            r'Min.*?Due.*?Rs\.?\s*([\d,]+\.\d{2})',
            r'Minimum.*?([\d,]+\.\d{2})'
        ],
        'credit_limit': [
            r'Credit Limit\s*:?\s*Rs\.?\s*([\d,]+\.\d{2})',
            r'Total.*?Limit.*?Rs\.?\s*([\d,]+\.\d{2})'
        ],
        'available_limit': [
            r'Available Credit\s*:?\s*Rs\.?\s*([\d,]+\.\d{2})',
            r'Available.*?Rs\.?\s*([\d,]+\.\d{2})'
        ]
    },
    'bob': {
        'card_number': [
            r'(\d{4})\s*\*+\s*(\d{4})',
            r'(\d{4})XXXXXXXX(\d{4})',
            r'Card.*?(\d{4})\*+(\d{4})'
        ],
        'statement_date': [
            r'Statement Date\s*:?\s*(\d{2}/\d{2}/\d{4})',
            r'Statement.*?(\d{2}-\d{2}-\d{4})',
            r'Date.*?(\d{2}/\d{2}/\d{4})'
        ],
        'total_due': [
            r'Total Amount Due\s*:?\s*([\d,]+\.\d{2})',
            r'Total.*?Due.*?([\d,]+\.\d{2})',
            r'Amount Due.*?([\d,]+\.\d{2})'
        ],
        'due_date': [
            r'Payment Due Date\s*:?\s*(\d{2}/\d{2}/\d{4})',
            r'Due Date.*?(\d{2}/\d{2}/\d{4})',
            r'Pay.*?by.*?(\d{2}/\d{2}/\d{4})'
        ],
        'min_due': [
            r'Minimum Amount Due\s*:?\s*([\d,]+\.\d{2})',
            r'Min.*?Due.*?([\d,]+\.\d{2})',
            r'Minimum.*?([\d,]+\.\d{2})'
        ],
        'credit_limit': [
            r'Credit Limit\s*:?\s*([\d,]+\.\d{2})',
            r'Total.*?Limit.*?([\d,]+\.\d{2})'
        ],
        'available_limit': [
            r'Available Credit\s*:?\s*([\d,]+\.\d{2})',
            r'Available.*?([\d,]+\.\d{2})'
        ]
    }
}

# --- DATE FORMAT CONFIGURATIONS ---
DATE_FORMATS = [
    '%d %b %Y',         # 15 Jan 2024
    '%d/%m/%Y',         # 15/01/2024
    '%d-%m-%Y',         # 15-01-2024
    '%d-%b-%Y',         # 15-Jan-2024
    '%B %d, %Y',        # January 15, 2024
    '%d %B %Y',         # 15 January 2024
    '%Y-%m-%d',         # 2024-01-15
    '%m/%d/%Y',         # 01/15/2024
    '%d.%m.%Y',         # 15.01.2024
]

# --- UTILITY FUNCTIONS ---
def _clean_and_convert_date(date_str, date_format=None):
    """Helper function to parse and standardize date strings."""
    if not date_str:
        return None
    
    # Try specific format first if provided
    if date_format:
        try:
            return datetime.strptime(date_str, date_format).strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            pass
    
    # Try all known formats
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            continue
    
    return None

def _clean_and_convert_amount(amount_str):
    """Helper function to clean and convert amount strings to float."""
    if not amount_str:
        return None
    try:
        # Remove currency symbols, commas, and extra spaces
        cleaned = re.sub(r'[₹$,\s]', '', str(amount_str))
        return float(cleaned)
    except (ValueError, TypeError):
        return None

def _is_valid_date(date_str, statement_date_str=None):
    """Checks if a date is valid and reasonable."""
    if not date_str:
        return False
    
    try:
        parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
        current_date = datetime.now()
        
        # Date cannot be more than 2 years in the future
        if parsed_date.year > current_date.year + 2:
            return False
            
        # Date cannot be more than ~18 months in the past
        if (current_date - parsed_date).days > 550:
            return False
            
        # If statement date exists, due date must be on or after it
        if statement_date_str:
            stmt_date = datetime.strptime(statement_date_str, '%Y-%m-%d')
            if parsed_date < stmt_date:
                return False
                
        return True
    except (ValueError, TypeError):
        return False

def _extract_with_multiple_patterns(text, patterns):
    """Try multiple regex patterns and return the first successful match."""
    if isinstance(patterns, str):
        patterns = [patterns]
    
    for pattern in patterns:
        try:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                return match
        except Exception as e:
            logger.debug(f"Pattern error: {e}")
            continue
    
    return None

# --- PDF TEXT EXTRACTION ---
def _extract_text_from_pdf(pdf_path, password):
    """Extracts text from a password-protected PDF using multiple methods."""
    text = ""
    
    # Method 1: Try pdfplumber (more accurate for layout)
    try:
        with pdfplumber.open(pdf_path, password=password) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if page_text:
                    text += page_text + "\n"
        if text.strip():
            return text
    except Exception as e:
        # Expected for some encrypted PDFs; keep quiet
        logger.debug(f"pdfplumber failed: {e}. Trying PyPDF2...")

    # Method 2: Fallback to PyPDF2
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            if pdf_reader.is_encrypted:
                pdf_reader.decrypt(password)
            
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    except Exception as e:
        # Some PDFs will not decrypt with given password
        logger.debug(f"PyPDF2 failed: {e}")
        return None

# --- COMPREHENSIVE PDF PARSING ---
def parse_pdf_content(pdf_text, bank_name):
    """Parses PDF text using comprehensive pattern matching for robustness."""
    bank_key = bank_name.lower()
    patterns = COMPREHENSIVE_BANK_PATTERNS.get(bank_key)

    if not patterns:
        logger.debug(f"No parsing patterns found for bank: {bank_name}")
        return {}

    result = {'bank_name': bank_name.upper()}
    
    # Extract card number with multiple pattern attempts
    card_match = _extract_with_multiple_patterns(pdf_text, patterns['card_number'])
    if card_match:
        groups = card_match.groups()
        if len(groups) == 1:
            result['card_last4'] = groups[0]
        elif len(groups) > 1:
            # For patterns with multiple groups, use the last one (usually the last 4 digits)
            result['card_last4'] = groups[-1]
    
    # Extract dates
    # Some banks (or certain formats) might not have a reliable statement_date field
    stmt_match = _extract_with_multiple_patterns(pdf_text, patterns.get('statement_date', []))
    due_match = _extract_with_multiple_patterns(pdf_text, patterns['due_date'])
    
    if stmt_match:
        result['statement_date'] = _clean_and_convert_date(stmt_match.group(1))
    
    if due_match:
        groups = due_match.groups()
        due_group = groups[0] if len(groups) == 1 else groups[-1]
        result['due_date'] = _clean_and_convert_date(due_group)
    
    # Extract amounts
    total_match = _extract_with_multiple_patterns(pdf_text, patterns['total_due'])
    if total_match:
        groups = total_match.groups()
        total_group = groups[0] if len(groups) == 1 else groups[-1]
        result['total_due'] = _clean_and_convert_amount(total_group)
    
    # Extract optional fields
    for field in ['min_due', 'credit_limit', 'available_limit']:
        if field in patterns:
            match = _extract_with_multiple_patterns(pdf_text, patterns[field])
            if match:
                groups = match.groups()
                amount_group = groups[0] if len(groups) == 1 else groups[-1]
                result[field] = _clean_and_convert_amount(amount_group)
    
    return result

def analyze_pdf(pdf_path, password, bank_name):
    """Main function to analyze PDF statements - orchestrates the entire process."""
    # No verbose logging - silent operation
    
    # Step 1: Extract text from PDF
    pdf_text = _extract_text_from_pdf(pdf_path, password)
    
    if not pdf_text:
        # Silent failure
        return None

    # Heuristic: Skip non-statement ICICI amortization schedule PDFs
    if bank_name.lower() == 'icici' and 'amortization schedule' in pdf_text.lower():
        return None
    
    # Step 2: Parse the extracted text
    parsed_data = parse_pdf_content(pdf_text, bank_name)
    
    # Step 3: Validate essential information - only require card_last4 and due_date
    # Statement date is optional
    essential_fields = ['card_last4', 'due_date']
    missing_fields = [field for field in essential_fields if not parsed_data.get(field)]
    
    if missing_fields:
        # Silent failure - no logging
        return None
    
    # Step 4: Validate dates - ensure the due date is valid
    if not _is_valid_date(parsed_data.get('due_date'), parsed_data.get('statement_date')):
        # Silent failure - no logging
        return None
    
    # Only validate chronological order if both dates exist
    stmt_str = parsed_data.get('statement_date')
    due_str = parsed_data.get('due_date')
    if stmt_str and due_str:
        try:
            stmt = datetime.strptime(stmt_str, '%Y-%m-%d')
            due = datetime.strptime(due_str, '%Y-%m-%d')
            # Only basic check that due date is on or after statement date
            if due < stmt:
                logger.debug(
                    f"Due date before statement date for {os.path.basename(pdf_path)}"
                )
                return None
        except Exception:
            pass

    return parsed_data

def test_parsing_patterns(pdf_path, password, bank_name):
    """Enhanced testing function for debugging patterns."""
    print(f"\n{'='*80}")
    print(f"COMPREHENSIVE PATTERN TEST - {bank_name.upper()}")
    print(f"{'='*80}")
    
    # Extract text
    passwords_to_try = password if isinstance(password, list) else [password]
    text = None
    for pwd in passwords_to_try:
        try:
            text = _extract_text_from_pdf(pdf_path, pwd)
            if text and len(text.strip()) > 100:
                print(f"✓ Text extracted with password: {pwd}")
                break
        except Exception as e:
            print(f"✗ Password '{pwd}' failed: {e}")
    
    if not text:
        print("✗ Could not extract any text")
        return
    
    # Test all patterns for this bank
    patterns = COMPREHENSIVE_BANK_PATTERNS.get(bank_name.lower(), {})
    if not patterns:
        print(f"✗ No patterns found for {bank_name}")
        return
    
    print(f"\nTesting {len(patterns)} pattern categories:")
    for field, pattern_list in patterns.items():
        print(f"\n--- {field.upper()} ---")
        match_found = False
        for i, pattern in enumerate(pattern_list):
            try:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                if match:
                    groups = match.groups()
                    result = groups[0] if len(groups) == 1 else groups
                    print(f"✓ Pattern {i+1}: {result}")
                    match_found = True
                    break
                else:
                    print(f"✗ Pattern {i+1}: No match")
            except Exception as e:
                print(f"✗ Pattern {i+1}: Error - {e}")
        
        if not match_found:
            print(f"  → All patterns failed for {field}")

# --- STANDALONE TESTING ---
if __name__ == '__main__':
    print("--- Comprehensive Parser Test Mode ---")
    
    # Load test configuration
    try:
        with open('creds/passwords.json', 'r') as f:
            passwords = json.load(f)
        
        rahul_passwords = passwords.get('rahul', {})
        
        # Test cases
        test_cases = [
            ('sbi', 'examples/sbi.pdf', rahul_passwords.get('sbi')),
            ('axis', 'examples/axis.pdf', rahul_passwords.get('axis')),
            ('indusind', 'examples/indusind.pdf', rahul_passwords.get('indusind')),
            ('icici', 'examples/icici.pdf', rahul_passwords.get('icici')),
            ('kotak', 'examples/kotak.pdf', rahul_passwords.get('kotak')),
            ('rbl', 'examples/rbl.pdf', rahul_passwords.get('rbl')),
            ('hdfc', 'examples/HDFC.PDF', rahul_passwords.get('hdfc', 'default')),
            ('bob', 'examples/BOB.pdf', rahul_passwords.get('bob', 'default')),
        ]
        
        for bank, filepath, password in test_cases:
            if os.path.exists(filepath):
                # Run comprehensive pattern test
                test_parsing_patterns(filepath, password, bank)
                
                # Run actual parsing
                data = analyze_pdf(filepath, password, bank)
                if data:
                    print(f"\n--- PARSED RESULT for {bank.upper()} ---")
                    print(json.dumps(data, indent=2))
                    print("-" * 50)
            else:
                print(f"Test file not found: {filepath}")
                
    except FileNotFoundError as e:
        print(f"Configuration file missing: {e}")
        print("Please ensure 'creds/passwords.json' exists for testing.")
