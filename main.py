import os
import json
from rich.console import Console
from rich.table import Table
from rich import box

# Import the comprehensive parser
from parser import analyze_pdf
# Import Gmail authentication functions
from gmail_auth import authenticate_gmail, get_statement_emails

# Database functions
import sqlite3
import pandas as pd

def init_db():
    conn = sqlite3.connect('credit_statements.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL,
            bank_name TEXT,
            card_last4 TEXT,
            statement_date TEXT,
            total_due REAL,
            due_date TEXT,
            min_due REAL,
            credit_limit REAL,
            available_limit REAL,
            UNIQUE(user, card_last4, statement_date)
        )
    ''')
    conn.commit()
    return conn

def insert_bill(conn, bill_data, user):
    c = conn.cursor()
    # Use due_date as fallback for statement_date to avoid NULL-based duplicates
    statement_date = bill_data.get('statement_date') or bill_data.get('due_date')
    c.execute('''
        INSERT OR IGNORE INTO bills (
            user, bank_name, card_last4, statement_date, total_due, due_date,
            min_due, credit_limit, available_limit
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user,
        bill_data.get('bank_name'),
        bill_data.get('card_last4'),
        statement_date,
        bill_data.get('total_due'),
        bill_data.get('due_date'),
        bill_data.get('min_due'),
        bill_data.get('credit_limit'),
        bill_data.get('available_limit')
    ))
    conn.commit()

def display_bills(conn, user):
    query = '''
        SELECT bank_name, card_last4, min_due, total_due, due_date, 
               available_limit, statement_date, credit_limit 
        FROM bills 
        WHERE user = ? 
        ORDER BY due_date
    '''
    df = pd.read_sql_query(query, conn, params=[user])
    # Drop duplicates in case older runs inserted multiple rows with NULL statement_date
    df = df.drop_duplicates(subset=['bank_name', 'card_last4', 'due_date'])
    if df.empty:
        console = Console()
        console.print(f"No bills found in the database for user '{user}'.", style="yellow")
        return
    
    # Format currency values and dates
    for col in ['min_due', 'total_due', 'available_limit', 'credit_limit']:
        df[col] = df[col].apply(lambda x: f"₹{float(x):,.2f}" if pd.notnull(x) else "N/A")
    
    console = Console()
    table = Table(title=f"Credit Card Bills - {user.capitalize()}", show_header=True, 
                 box=box.HORIZONTALS)
    table.add_column("Bank")
    table.add_column("Card")
    table.add_column("Min Due")
    table.add_column("Total Due")
    table.add_column("Due Date")
    table.add_column("Available Limit")
    table.add_column("Statement Date")
    table.add_column("Credit Limit")

    for _, row in df.iterrows():
        table.add_row(
            row['bank_name'], row['card_last4'], row['min_due'], 
            row['total_due'], row['due_date'], row['available_limit'],
            row['statement_date'] or "N/A", row['credit_limit']
        )
    
    # Force the table to be printed
    console.print("\n")
    console.print(table)
    console.print("\n")
# --- END MOCK DB AND UTILS ---


# --- CONFIGURATION ---
USERS = ['rahul', 'gulshan'] # Add users you want to process
DAYS_TO_SEARCH = 45 # As per your project description

# Note: We're not filtering cards anymore - showing all valid cards
# that meet statement/due date requirements

def cleanup_disallowed_cards(conn, user):
    """Function kept for compatibility but no longer filters cards."""
    # No filtering - all cards are allowed as long as they have valid dates
    pass

def main():
    """Main function to orchestrate the credit card tracking process."""
    # Use Rich console for better output
    console = Console()
    console.print("[bold green]Credit Card Statement Tracker[/bold green]", justify="center")
    console.print("[dim]Automatically fetches and parses your credit card statements[/dim]", justify="center")
    console.print()
    
    # Suppress verbose/DEBUG output from libraries
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    creds_dir = os.path.join(base_dir, 'creds') # Expects a 'creds' sub-folder

    # Load configuration files
    try:
        with open(os.path.join(creds_dir, 'passwords.json'), 'r') as f:
            passwords = json.load(f)
        with open('cc_statements.txt', 'r') as f:
            statement_senders = [line.strip() for line in f if line.strip()]
    except FileNotFoundError as e:
        print(f"ERROR: Configuration file not found - {e}. Please ensure 'passwords.json' (in creds folder) and 'cc_statements.txt' exist.")
        return

    # Create a mapping from domain to bank name (matching passwords.json keys)
    # e.g. {'rblbank.com': 'rbl', ...}
    domain_to_bank = {}
    for bank in passwords.get('rahul', {}):
        for domain in statement_senders:
            if bank in domain or domain.startswith(bank):
                domain_to_bank[domain] = bank


    # Initialize database
    conn = init_db()
    
    console = Console()
    for user in USERS:
        console.print(f"\n[blue]Processing for user: {user}[/blue]")
        user_passwords = passwords.get(user, {})
        if not user_passwords:
            console.print(f"WARNING: No passwords found for user '{user}' in passwords.json. Skipping.", style="red")
            continue

        service = authenticate_gmail(user, creds_dir)
        if not service:
            continue

        emails = get_statement_emails(service, statement_senders, DAYS_TO_SEARCH)

        if not emails:
            console.print(f"No new statement emails found for {user}.", style="yellow")
            continue
            
        # We'll collect successful cards to display later
        successful_cards = []

        for email in emails:
            # Determine the bank based on the sender domain
            bank_name = None
            sender_lower = email['sender'].lower()
            for domain, bank in domain_to_bank.items():
                if domain in sender_lower:
                    bank_name = bank
                    break

            if not bank_name:
                # Silent failure
                continue

            password = user_passwords.get(bank_name)
            if not password:
                # Silent failure
                continue
            
            # Handle password lists (like SBI) - try each password until one works
            passwords_to_try = password if isinstance(password, list) else [password]
            
            parsed_data = None
            for pwd in passwords_to_try:
                # To use analyze_pdf, we need to write the data to a temporary file
                temp_pdf_path = f"temp_{email['filename']}"
                with open(temp_pdf_path, 'wb') as f:
                    f.write(email['pdf_data'])
                
                # Call the analysis function from the other module
                parsed_data = analyze_pdf(temp_pdf_path, pwd, bank_name)
                
                # Clean up the temporary file
                os.remove(temp_pdf_path)
                
                if parsed_data:
                    break  # Success with this password, no need to try others
                # Silent on password failures

            if parsed_data:
                # All valid parsed statements are accepted
                insert_bill(conn, parsed_data, user)
                card_num = parsed_data.get('card_last4', 'Unknown')
                bank = parsed_data.get('bank_name', 'Unknown')
                # Save for summary display later
                successful_cards.append((bank, card_num))
            # Failures are now silent

        # Clean up any disallowed cards
        cleanup_disallowed_cards(conn, user)
        
        # Display success message for each card
        if successful_cards:
            console.print("\n[bold]Successfully parsed:[/bold]")
            for bank, card_num in successful_cards:
                console.print(f"    [green]✓[/green] {bank} [yellow]{card_num}[/yellow]")
        
        # Display the nicely formatted table
        display_bills(conn, user)
    
    conn.close()

if __name__ == '__main__':
    main()
