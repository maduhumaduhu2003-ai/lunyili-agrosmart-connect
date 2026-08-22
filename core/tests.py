from django.test import TestCase
from django.urls import reverse
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone

from core.models import (
    Buyer,
    BuyingRequest,
    Category,
    Farmer,
    MarketPrice,
    Product,
    Supplier,
    USSDSession,
    User,
    FinancialInstitution,
    LoanApplication,
    LoanProduct,
    Order,
    Loan,
    LoanStatus,
    Repayment,
    RepaymentStatus,
    PaymentTransactionStatus,
    SMSMessage,
    SMSStatus,
)
from core.services.ussd_engine import USSDEngine
from core.services.repayment_service import (
    confirm_payment,
    generate_repayment_schedule,
    initiate_payment,
)


class USSDEngineSupplierLocationTests(TestCase):
    def test_supplier_matches_by_location_when_region_and_district_are_blank(self):
        user = User.objects.create_user(
            username='supplier_morogoro',
            email='supplier@example.com',
            phone='0710000000',
            password='Test@1234',
            role='SUPPLIER',
        )

        supplier = Supplier.objects.create(
            user=user,
            company_name='Morogoro Agro Hub',
            phone='0710000000',
            location='Morogoro, Mvomero',
            region='Morogoro',
            district='Mvomero',
            ward='Mzumbe',
            village='Mzumbe',
            is_verified='PENDING',
            is_active=True,
        )

        category = Category.objects.create(name='Seeds')
        product = Product.objects.create(
            category=category,
            supplier=supplier,
            name='Maize Seed',
            price=5000,
            stock=20,
            unit='kg',
            is_available=True,
        )

        session = USSDSession.objects.create(
            session_id='test_session_1',
            phone_number='+255750941683',
            current_screen='order_location_choice',
            state_data={
                'data': {
                    'product_id': str(product.id),
                    'farmer_region': 'Morogoro',
                    'farmer_district': 'Mvomero',
                }
            },
        )

        engine = USSDEngine(session=session, phone_number='+255750941683')
        response_type, response_text = engine._show_product_suppliers('Morogoro', 'region')

        self.assertEqual(response_type, 'CON')
        self.assertIn('Morogoro Agro Hub', response_text)
        self.assertNotIn('Hakuna muuzaji', response_text)

    def test_buyer_search_asks_for_region_then_lists_buyers_with_prices(self):
        buyer_user = User.objects.create_user(
            username='buyer_morogoro',
            email='buyer@example.com',
            phone='0711111111',
            password='Test@1234',
            role='BUYER',
        )

        buyer = buyer_user.buyer_profile if hasattr(buyer_user, 'buyer_profile') else None
        if buyer is None:
            from core.models import Buyer
            buyer = Buyer.objects.create(
                user=buyer_user,
                company_name='Morogoro Grain Buyers',
                phone='0711111111',
                location='Morogoro',
                is_verified='VERIFIED',
                is_active=True,
            )

        farmer = Farmer.objects.create(
            full_name='Test Farmer',
            phone_number='+255700000001',
            region='Morogoro',
            district='Mvomero',
            village='Mzumbe',
            ward='Mzumbe',
        )

        request = BuyingRequest.objects.create(
            buyer=buyer,
            crop='Maize',
            quantity_kg=50,
            price_offered=900,
            location='Morogoro',
            expiry_date='2030-12-31',
            is_open=True,
        )

        session = USSDSession.objects.create(
            session_id='buyer_session_1',
            phone_number='+255700000001',
            current_screen='main',
            state_data={'data': {}},
        )

        engine = USSDEngine(session=session, phone_number='+255700000001')
        engine.data['crops'] = ['Maize']
        response_type, response_text = engine._handle_buyer_crop('', '1')

        self.assertEqual(response_type, 'CON')
        self.assertIn('Andika mkoa au wilaya', response_text)
        self.assertIn('Maize', response_text)

        response_type, response_text = engine._handle_buyer_search_region('', 'Morogoro')

        self.assertEqual(response_type, 'CON')
        self.assertIn('Morogoro Grain Buyers', response_text)
        self.assertIn('Bei: TSh 900/kg', response_text)

    def test_start_buyers_lists_all_known_crops_not_just_farmer_primary_crop(self):
        from core.models import BuyingRequest, Farmer, MarketPrice

        Farmer.objects.create(
            full_name='Test Farmer',
            phone_number='+255700000002',
            region='Morogoro',
            district='Mvomero',
            village='Mzumbe',
            ward='Mzumbe',
            primary_crop='Maize',
        )

        MarketPrice.objects.create(
            crop='Rice',
            market='Morogoro',
            region='Morogoro',
            price=700,
            unit='kg',
        )
        BuyingRequest.objects.create(
            buyer=Buyer.objects.create(
                user=User.objects.create_user(
                    username='buyer_rice_2',
                    email='buyer2@example.com',
                    phone='0712222222',
                    password='Test@1234',
                    role='BUYER',
                ),
                company_name='Rice Buyers Ltd',
                phone='0712222222',
                location='Morogoro',
                is_verified='VERIFIED',
                is_active=True,
            ),
            crop='Beans',
            quantity_kg=40,
            price_offered=600,
            location='Morogoro',
            expiry_date='2030-12-31',
            is_open=True,
        )

        session = USSDSession.objects.create(
            session_id='buyer_session_2',
            phone_number='+255700000002',
            current_screen='main',
            state_data={'data': {}},
        )

        engine = USSDEngine(session=session, phone_number='+255700000002')
        response_type, response_text = engine._start_buyers()

        self.assertEqual(response_type, 'CON')
        self.assertIn('Maize', response_text)
        self.assertIn('Rice', response_text)
        self.assertIn('Beans', response_text)


class InputLoanWorkflowTests(TestCase):
    def setUp(self):
        self.farmer = Farmer.objects.create(
            full_name='Input Loan Farmer',
            phone_number='+255700000010',
            village='Mzumbe',
            district='Mvomero',
            primary_crop='Maize',
            credit_readiness_score=60,
        )
        supplier_user = User.objects.create_user(
            username='input_supplier', password='Test@1234', role='SUPPLIER'
        )
        self.supplier = Supplier.objects.create(
            user=supplier_user, company_name='Input Supplier', phone='0710000010'
        )
        institution_user = User.objects.create_user(
            username='input_finance', password='Test@1234', role='FINANCIAL'
        )
        self.institution = FinancialInstitution.objects.create(
            user=institution_user,
            institution_name='Input Finance',
            institution_type='MFI',
            phone='0710000011',
        )
        self.loan_product = LoanProduct.objects.create(
            institution=self.institution,
            name='Pembejeo Starter',
            loan_type='INPUT',
            interest_rate=10,
            min_amount=Decimal('10000'),
            max_amount=Decimal('500000'),
            duration_months=6,
            minimum_credit_score=50,
        )
        category = Category.objects.create(name='Fertilizer')
        self.product = Product.objects.create(
            category=category,
            supplier=self.supplier,
            name='Fertilizer',
            price=Decimal('10000'),
            stock=10,
            unit='kg',
        )

    def test_input_loan_creates_pending_application_and_unpaid_order(self):
        session = USSDSession.objects.create(
            session_id='input_loan_session',
            phone_number=self.farmer.phone_number,
            current_screen='financial_confirm',
            state_data={'data': {
                'input_product_id': str(self.product.id),
                'input_quantity': 2,
                'loan_amount': '20000',
                'loan_purpose': 'Mbolea',
                'selected_product_id': str(self.loan_product.id),
                'selected_product_name': self.loan_product.name,
            }},
        )
        engine = USSDEngine(session, self.farmer.phone_number)
        engine._send_sms = lambda *args, **kwargs: None

        response_type, _ = engine._create_input_loan(self.farmer)

        application = LoanApplication.objects.get(farmer=self.farmer)
        order = Order.objects.get(farmer=self.farmer)
        self.assertEqual(response_type, 'END')
        self.assertEqual(application.loan_product, self.loan_product)
        self.assertEqual(application.order, order)
        self.assertEqual(order.status, 'LOAN_PENDING')
        self.assertEqual(order.payment_status, 'PENDING')
        self.assertEqual(self.product.stock, 10)

        with self.assertRaises(ValueError):
            engine._create_input_loan(self.farmer)

    def test_financial_dashboard_requires_financial_role(self):
        user = User.objects.create_user(
            username='ordinary_user', password='Test@1234', role='SUPPLIER'
        )
        self.client.force_login(user)
        response = self.client.get(reverse('financial_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_disbursement_generates_product_based_schedule_once(self):
        application = LoanApplication.objects.create(
            farmer=self.farmer,
            loan_product=self.loan_product,
            amount=Decimal('120000'),
            status=LoanStatus.APPROVED,
        )
        finance_user = self.institution.user
        self.client.force_login(finance_user)

        with patch('core.views_financial.send_event_sms'):
            response = self.client.post(
                reverse('financial_application_detail', args=[application.id]),
                {'action': 'disburse'},
            )

        self.assertEqual(response.status_code, 302)
        loan = Loan.objects.get(application=application)
        self.assertEqual(loan.status, LoanStatus.DISBURSED)
        self.assertEqual(loan.interest_amount, Decimal('12000.00'))
        self.assertEqual(loan.repayments.count(), 6)
        generate_repayment_schedule(loan)
        self.assertEqual(loan.repayments.count(), 6)

    def test_partial_and_duplicate_payment_confirmation_are_safe(self):
        application = LoanApplication.objects.create(
            farmer=self.farmer,
            loan_product=self.loan_product,
            amount=Decimal('120000'),
            status=LoanStatus.DISBURSED,
        )
        loan = Loan.objects.create(
            application=application,
            principal_amount=Decimal('120000'),
            interest_amount=Decimal('12000'),
            outstanding_balance=Decimal('132000'),
            status=LoanStatus.DISBURSED,
            disbursed_at=timezone.now(),
        )
        generate_repayment_schedule(loan)
        payment = initiate_payment(loan, Decimal('5000'))
        payment = confirm_payment(payment.provider_reference, {'status': 'confirmed'})
        self.assertEqual(loan.repayments.get(installment_number=1).status, RepaymentStatus.PARTIALLY_PAID)
        self.assertEqual(PaymentTransactionStatus.CONFIRMED, payment.status)
        balance = Loan.objects.get(pk=loan.pk).outstanding_balance

        confirm_payment(payment.provider_reference, {'status': 'confirmed'})
        self.assertEqual(Loan.objects.get(pk=loan.pk).outstanding_balance, balance)

    def test_payment_callback_confirms_only_provider_reference(self):
        application = LoanApplication.objects.create(
            farmer=self.farmer,
            loan_product=self.loan_product,
            amount=Decimal('120000'),
            status=LoanStatus.DISBURSED,
        )
        loan = Loan.objects.create(
            application=application,
            principal_amount=Decimal('120000'),
            outstanding_balance=Decimal('120000'),
            status=LoanStatus.DISBURSED,
            disbursed_at=timezone.now(),
        )
        generate_repayment_schedule(loan)
        payment = initiate_payment(loan, Decimal('132000'))
        with patch('core.views_ussd.send_event_sms'):
            response = self.client.post(reverse('payment_callback'), {
                'provider_reference': payment.provider_reference,
                'status': 'success',
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Loan.objects.get(pk=loan.pk).status, LoanStatus.REPAID)

    def test_failed_payment_callback_does_not_change_balance(self):
        application = LoanApplication.objects.create(
            farmer=self.farmer,
            loan_product=self.loan_product,
            amount=Decimal('120000'),
            status=LoanStatus.DISBURSED,
        )
        loan = Loan.objects.create(
            application=application,
            principal_amount=Decimal('120000'),
            outstanding_balance=Decimal('120000'),
            status=LoanStatus.DISBURSED,
            disbursed_at=timezone.now(),
        )
        generate_repayment_schedule(loan)
        payment = initiate_payment(loan, Decimal('5000'))
        response = self.client.post(reverse('payment_callback'), {
            'provider_reference': payment.provider_reference,
            'status': 'failed',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PaymentTransactionStatus.FAILED, payment.__class__.objects.get(pk=payment.pk).status)
        self.assertEqual(Loan.objects.get(pk=loan.pk).outstanding_balance, Decimal('132000'))

    def test_event_sms_is_idempotent(self):
        from core.services.notification_service import send_event_sms
        with patch('core.services.africastalking_service.AfricaTalkingService.send_sms', return_value={'status': 'queued'}):
            send_event_sms('test-event-1', self.farmer.phone_number, 'Taarifa ya majaribio')
            send_event_sms('test-event-1', self.farmer.phone_number, 'Taarifa ya majaribio')
        self.assertEqual(SMSMessage.objects.filter(event_key='test-event-1').count(), 1)
        self.assertEqual(SMSMessage.objects.get(event_key='test-event-1').status, SMSStatus.QUEUED)

    def test_financial_menu_contains_repayment_options(self):
        session = USSDSession.objects.create(
            session_id='financial_menu_session',
            phone_number=self.farmer.phone_number,
            current_screen='financial_menu',
            state_data={'data': {}},
        )
        response_type, response = USSDEngine(session, self.farmer.phone_number)._render_financial_menu(), None
        self.assertIn('7. Ratiba ya Marejesho', response_type)
        self.assertIn('8. Malipo', response_type)

    def test_progressive_profile_collects_one_field(self):
        session = USSDSession.objects.create(
            session_id='profile_session',
            phone_number=self.farmer.phone_number,
            current_screen='financial_collect_data',
            state_data={'data': {}},
        )
        engine = USSDEngine(session, self.farmer.phone_number)
        response_type, response = engine._handle_financial_collect_data('', '1')
        self.assertEqual(response_type, 'CON')
        self.assertIn('Jinsia', response)
        response_type, _ = engine._handle_financial_profile_value('', 'F')
        self.assertEqual(response_type, 'CON')
        self.assertEqual(Farmer.objects.get(pk=self.farmer.pk).gender, 'F')
