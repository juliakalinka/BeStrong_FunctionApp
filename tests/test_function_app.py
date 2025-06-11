import unittest
import json
from function_app import process_pdf, extract_structured_data
import azure.functions as func

class TestFunctionApp(unittest.TestCase):
    def test_process_pdf_missing_filename(self):
        # Створюємо тестовий запит без filename
        req = func.HttpRequest(
            method='GET',
            body=None,
            url='/api/process-pdf',
            params={}
        )
        
        # Викликаємо функцію
        response = process_pdf(req)
        
        # Перевіряємо результат
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_body().decode(), "Please provide file_name parameter")

    def test_extract_structured_data(self):
        # Тестовий вхідний текст
        test_content = """
        Company Name
        123 Business Street
        City, Country
        VAT No.: 123456789
        
        Address Where Meter Installed:
        456 Customer Street
        Customer City
        
        Invoice Number: INV123
        Invoice Date: 2024-03-20
        Payment Due Date: 2024-04-20
        
        12345
        Generation
        1000
        2024-02-20
        2000
        2024-03-20
        
        Billing Period: Feb 2024
        Cost per kWh: 0.15
        Total Consumption: 1000
        Net Cost: 150.00
        VAT @ 20%
        Total Amount Due: 180.00
        
        Account Name: Test Account
        Bank Sort Code: 12-34-56
        Account Number: 12345678
        """
        
        result = extract_structured_data(test_content)
        
        # Перевіряємо основні поля
        self.assertIn('company_info', result)
        self.assertIn('customer_info', result)
        self.assertIn('invoice_details', result)
        self.assertIn('meter_readings', result)
        self.assertIn('billing_details', result)
        self.assertIn('payment_details', result)
        
        # Перевіряємо конкретні значення
        self.assertEqual(result['invoice_details']['number'], 'INV123')
        self.assertEqual(len(result['meter_readings']), 1)
        self.assertEqual(result['billing_details']['total'], '180.00')

if __name__ == '__main__':
    unittest.main() 