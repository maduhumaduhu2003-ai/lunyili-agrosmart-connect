
from __future__ import annotations
import logging
from decimal import Decimal
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from ..models import (
    Farmer, Product, Category, Order, OrderItem, 
    LoanApplication, SMSMessage, Supplier, User,
    MarketPrice, BuyingRequest, Advice, WeatherData,
    WeatherAlert, USSDStatus, Buyer, InterestedFarmer,
    LoanProduct, FinancialInstitution, Loan, LoanStatus, Repayment,
    RepaymentStatus, PaymentTransactionStatus
)
from .repayment_service import initiate_payment
from .disbursement_service import request_disbursement
from .kyc_service import validate_nida_format

logger = logging.getLogger(__name__)

CON = "CON"
END = "END"

BACK = "0"
HOME = "00"
CANCEL = "#"


def screen_main_menu() -> str:
    """Main menu screen"""
    return (
        "Karibu Lunyili AgroSmart Connect\n"
        "1. Jisajili\n"
        "2. Agiza Pembejeo\n"
        "3. Bei za Soko\n"
        "4. Tafuta Wanunuzi\n"
        "5. Ushauri wa Kilimo\n"
        "6. Hali ya Hewa\n"
        "7. Huduma za Kifedha\n"
        "0. Mwisho\n"
        "# Ghairi | 00 Nyumbani"
    )


def _error(msg: str = "Chaguo batili. Jaribu tena.") -> str:
    return msg


def _menu(title: str, options: list) -> str:
    lines = [title] + options
    return "\n".join(lines)


def _get_last_input(text: str) -> str:
    """Get the last part of USSD input (after the last *)"""
    if not text:
        return ""
    parts = text.split('*')
    return parts[-1] if parts else ""


def _normalize_number_input(value: str) -> str:
    """Strip common punctuation from numeric user input."""
    if not value:
        return ""
    return ''.join(ch for ch in value if ch.isdigit())


def _parse_int(value: str) -> int | None:
    try:
        clean = _normalize_number_input(value)
        return int(clean) if clean else None
    except ValueError:
        return None


def _parse_decimal(value: str) -> Decimal | None:
    try:
        clean = ''.join(ch for ch in value if ch.isdigit() or ch == '.')
        return Decimal(clean) if clean else None
    except Exception:
        return None


class USSDEngine:
    """Complete USSD state machine"""
    
    def __init__(self, session, phone_number: str):
        self.session = session
        self.phone_number = phone_number
        self.state = session.state_data or {}
        self.data = self.state.setdefault("data", {})
        self.history = self.state.setdefault("_history", [])
        self.path = session.current_screen or "main"
        self.logger = logging.getLogger(__name__)
        self.timeout_seconds = getattr(settings, 'USSD_SESSION_TIMEOUT', 1800)

    def _goto(self, next_path: str, keep_data: bool = True):
        if self.path != next_path:
            self.history.append(self.path)
        self.path = next_path
        if not keep_data:
            self.data.clear()

    def _save(self):
        """Save session state and extend session lifetime"""
        self.state["data"] = self.data
        self.state["_history"] = self.history
        from .session_service import USSDSessionService
        
        USSDSessionService.save_state(
            session=self.session,
            current_screen=self.path,
            state_data=self.state,
            last_input=self.state.get("_last_input", "")
        )
        
        self.session.updated_at = timezone.now()
        self.session.save(update_fields=['updated_at'])

    def _end(self):
        from .session_service import USSDSessionService
        USSDSessionService.end_session(session=self.session)

    def _is_session_expired(self) -> bool:
        """Check if session has expired"""
        age = (timezone.now() - self.session.updated_at).total_seconds()
        return age > self.timeout_seconds

    def _extend_session(self):
        """Extend session lifetime"""
        self.session.updated_at = timezone.now()
        self.session.save(update_fields=['updated_at'])
        logger.debug(f"Session {self.session.session_id} extended")

    def _send_sms(self, phone_number: str, message: str):
        """Send SMS using Africa's Talking with Sender ID agrosmart"""
        try:
            sms = SMSMessage.objects.create(
                recipient=phone_number,
                message=message,
                status='QUEUED'
            )
            
            from .africastalking_service import AfricaTalkingService
            service = AfricaTalkingService()
            result = service.send_sms(
                phone_number=phone_number,
                message=message
            )
            
            logger.info(f"SMS Result for {phone_number}: {result}")
            
            if result.get('status') == 'sent':
                data = result.get('data', {})
                recipients = data.get('SMSMessageData', {}).get('Recipients', [])
                
                if recipients:
                    sms.mark_sent(
                        provider_message_id=recipients[0].get('messageId', ''),
                        provider_response=result,
                        cost=recipients[0].get('cost', None)
                    )
                    logger.info(f"SMS sent to {phone_number} from agrosmart")
                else:
                    sms.mark_failed("No recipients in response")
                    logger.error(f"SMS failed - no recipients: {result}")
            else:
                error_msg = result.get('message', 'Unknown error')
                sms.mark_failed(error_msg)
                logger.error(f"SMS failed to {phone_number}: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error sending SMS: {str(e)}")
            try:
                SMSMessage.objects.create(
                    recipient=phone_number,
                    message=message,
                    status='FAILED',
                    error_message=str(e)
                )
            except:
                pass

    def step(self, user_input: str):
        """Process user input and return response"""
        user_input = (user_input or "").strip()
        self.state["_last_input"] = user_input
        last_input = _get_last_input(user_input)

        try:
            if self._is_session_expired():
                logger.warning(f"Session {self.session.session_id} expired, resetting")
                self._goto("main", keep_data=False)
                self._save()
                return CON, screen_main_menu()

            if self.path == "main" and user_input == "":
                self._goto("main", keep_data=False)
                self._save()
                return CON, screen_main_menu()

            if last_input == CANCEL:
                self._end()
                return END, "Umeghairi kikao. Piga *566# wakati wowote."

            if last_input == HOME:
                self._goto("main", keep_data=False)
                self._save()
                return CON, screen_main_menu()

            if last_input == BACK and self.history:
                self.path = self.history.pop()
                self._save()
                return CON, self._render_current_screen()

            handler = getattr(self, f"_handle_{self.path}", None)
            if handler is None:
                self._goto("main", keep_data=False)
                self._save()
                return CON, screen_main_menu()

            status, screen = handler(user_input, last_input)
            if status == END:
                self._end()
            else:
                self._save()
                self._extend_session()
            return status, screen
            
        except Exception as e:
            self.logger.error(f"Error in step: {str(e)}")
            self._end()
            return END, "Samahani, kuna tatizo. Jaribu tena baadaye."

    def _render_current_screen(self) -> str:
        renderer = getattr(self, f"_render_{self.path}", None)
        if renderer:
            return renderer()
        return screen_main_menu()

    # ======================================================================
    # MAIN MENU
    # ======================================================================
    def _handle_main(self, full_text: str, last_input: str):
        routes = {
            "1": self._start_register,
            "2": self._start_order,          # Kununua Pembejeo tu
            "3": self._start_prices,
            "4": self._start_buyers,          # Tafuta Wanunuzi (Kuuza Mazao)
            "5": self._start_advice,
            "6": self._start_weather,
            "7": self._start_financial,
            "0": self._exit,
        }
        starter = routes.get(last_input)
        if starter is None:
            return CON, _error() + "\n\n" + screen_main_menu()
        return starter()

    def _exit(self):
        self._end()
        return END, "Asante kwa kutumia Lunyili AgroSmart. Piga *566# wakati wowote."

    # ======================================================================
    # 1. REGISTER
    # ======================================================================
    def _start_register(self):
        if Farmer.objects.filter(phone_number=self.phone_number).exists():
            farmer = Farmer.objects.get(phone_number=self.phone_number)
            self._end()
            return END, (
                f"Tayari umesajiliwa!\n"
                f"Jina: {farmer.full_name}\n"
                f"Eneo: {farmer.region}, {farmer.district}\n"
                f"Zao: {farmer.primary_crop or 'Halijawekwa'}\n"
                f"Piga *566# tena kutumia huduma."
            )
        self._goto("register_name")
        return CON, "Jisajili\nAndika jina lako kamili:"

    def _handle_register_name(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika jina lako kamili (herufi 2 au zaidi):"
        self.data["full_name"] = last_input.strip()
        self._goto("register_gender")
        return CON, "Jinsia:\n1. Mwanaume\n2. Mwanamke"

    def _handle_register_gender(self, full_text: str, last_input: str):
        if last_input == "1":
            self.data["gender"] = "M"
            self._goto("register_region")
            return CON, "Andika mkoa wako:"
        elif last_input == "2":
            self.data["gender"] = "F"
            self._goto("register_region")
            return CON, "Andika mkoa wako:"
        else:
            return CON, _error() + "\nChagua 1 kwa Mwanaume au 2 kwa Mwanamke:"

    def _handle_register_region(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika mkoa wako:"
        self.data["region"] = last_input.strip()
        self._goto("register_district")
        return CON, "Andika wilaya:"

    def _handle_register_district(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika wilaya:"
        self.data["district"] = last_input.strip()
        self._goto("register_ward")
        return CON, "Andika kata:"

    def _handle_register_ward(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika kata:"
        self.data["ward"] = last_input.strip()
        self._goto("register_village")
        return CON, "Andika kijiji:"

    def _handle_register_village(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika kijiji:"
        self.data["village"] = last_input.strip()
        self._goto("register_crop")
        return CON, "Andika zao lako kuu (mfano: Mahindi):"

    def _handle_register_crop(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika zao lako kuu:"
        
        try:
            farmer = Farmer.objects.create(
                full_name=self.data.get("full_name", ""),
                phone_number=self.phone_number,
                region=self.data.get("region", ""),
                district=self.data.get("district", ""),
                ward=self.data.get("ward", ""),
                village=self.data.get("village", ""),
                gender=self.data.get("gender", ""),
                primary_crop=last_input.strip(),
                registered_via="USSD"
            )
            
            self._send_sms(
                farmer.phone_number,
                f"Karibu {farmer.full_name}! Umesajiliwa Lunyili AgroSmart. "
                f"Piga *566# kupata huduma za kilimo."
            )
            
            self._end()
            return END, (
                f"Umefanikiwa kujisajili {farmer.full_name}!\n"
                f"Piga *566# wakati wowote kupata huduma."
            )
            
        except Exception as e:
            self.logger.error(f"Registration error: {str(e)}")
            self._end()
            return END, "Samahani, imeshindikana kujisajili. Jaribu tena."

# ======================================================================
# 2. ORDER - KUNUNUA PEMBEJEO 
# ======================================================================
    def _start_order(self):

        farmer = Farmer.objects.filter(
            phone_number=self.phone_number
        ).first()

        if not farmer:
            return END, (
                "Jisajili kwanza.\n"
                "Chagua 1 kwenye menu kuu."
            )

        # ---------------------------------------------------------------
        # SAVE FARMER INFORMATION
        # ---------------------------------------------------------------

        self.data["farmer_id"] = str(farmer.id)
        self.data["farmer_region"] = farmer.region or ""
        self.data["farmer_district"] = farmer.district or ""
        self.data["farmer_village"] = farmer.village or ""

        # ---------------------------------------------------------------
        # GET ACTIVE CATEGORIES
        # ---------------------------------------------------------------

        categories = list(
            Category.objects.filter(
                is_active=True
            )
            .order_by("name")[:9]
        )

        if not categories:
            self._end()
            return END, (
                "Samahani, hakuna bidhaa "
                "zilizopo kwa sasa."
            )

        self.data["category_ids"] = [
            str(category.id)
            for category in categories
        ]

        self._goto("order_category")

        lines = [
            f"{index + 1}. {category.name}"
            for index, category in enumerate(categories)
        ]

        lines.append("0. Rudi Menu")

        return CON, _menu(
            "AGIZA PEMBEJEO\n"
            "Chagua kundi la bidhaa:",
            lines
        )


    # ======================================================================
    # ORDER CATEGORY
    # ======================================================================

    def _handle_order_category(
        self,
        full_text: str,
        last_input: str
    ):
        """
        Category -> Product
        """

        if last_input == "0":
            self._end()
            return END, (
                "Asante kwa kutumia "
                "Lunyili AgroSmart."
            )

        idx = _parse_int(last_input)

        if idx is None or idx < 1:
            return CON, (
                _error() +
                "\nChagua namba sahihi (1-9):"
            )

        try:
            category_id = self.data[
                "category_ids"
            ][idx - 1]

        except (IndexError, KeyError):
            return CON, (
                _error() +
                "\nChagua namba sahihi (1-9):"
            )

        try:
            category = Category.objects.get(
                id=category_id,
                is_active=True
            )

        except Category.DoesNotExist:
            return CON, (
                "Samahani, kundi hili "
                "halipatikani.\n"
                "Chagua kundi lingine:"
            )

        self.data["selected_category_id"] = (
            str(category.id)
        )

        self.data["category_name"] = (
            category.name
        )

        # ---------------------------------------------------------------
        # GET AVAILABLE PRODUCTS
        # ---------------------------------------------------------------

        products = list(
            Product.objects.filter(
                category=category,
                is_available=True
            )
            .select_related(
                "supplier",
                "category"
            )
            .order_by("name")[:9]
        )

        if not products:
            self._goto("order_category")

            return CON, (
                f"Hakuna bidhaa zinazopatikana "
                f"kwenye kundi {category.name}.\n\n"
                "Chagua kundi lingine:"
            )

        self.data["product_ids"] = [
            str(product.id)
            for product in products
        ]

        self._goto("order_product")

        lines = []

        for index, product in enumerate(products):
            stock_status = "Ipo" if product.stock > 0 else "Imeisha"
            lines.append(
                f"{index + 1}. {product.name}\n"
                f"   TSh {int(product.price):,}/"
                f"{product.unit} | {stock_status}"
            )

        lines.append("0. Rudi Makundi")

        return CON, _menu(
            f"{category.name.upper()}\n"
            "Chagua bidhaa:",
            lines
        )


    # ======================================================================
    # ORDER PRODUCT
    # ======================================================================

    def _handle_order_product(
        self,
        full_text: str,
        last_input: str
    ):
        """
        Farmer selects exact product.

        Product selected here is only the product.
        Supplier is selected afterwards.
        """

        if last_input == "0":

            self._goto("order_category")

            return CON, self._render_order_category()

        idx = _parse_int(last_input)

        if idx is None or idx < 1:

            return CON, (
                _error() +
                "\nChagua namba sahihi ya bidhaa:"
            )

        try:

            product_id = self.data[
                "product_ids"
            ][idx - 1]

        except (
            IndexError,
            KeyError
        ):

            return CON, (
                _error() +
                "\nChagua namba sahihi ya bidhaa:"
            )

        try:

            product = (
                Product.objects
                .select_related(
                    "supplier",
                    "category"
                )
                .get(
                    id=product_id,
                    is_available=True
                )
            )

        except Product.DoesNotExist:

            return CON, (
                "Samahani, bidhaa hii "
                "haipatikani."
            )

        # ---------------------------------------------------------------
        # SAVE PRODUCT
        # ---------------------------------------------------------------

        self.data["product_id"] = str(
            product.id
        )

        self.data["product_name"] = (
            product.name
        )

        self.data["product_unit"] = (
            product.unit
        )

        self.data["product_stock"] = (
            product.stock
        )

        self.data["product_price"] = (
            str(product.price)
        )

        self.data["category_name"] = (
            product.category.name
            if product.category
            else self.data.get(
                "category_name",
                ""
            )
        )

        # ---------------------------------------------------------------
        # ASK SEARCH LOCATION
        # ---------------------------------------------------------------

        self._goto(
            "order_location_choice"
        )

        farmer_region = (
            self.data.get(
                "farmer_region",
                ""
            )
        )

        farmer_district = (
            self.data.get(
                "farmer_district",
                ""
            )
        )

        stock_status = "Ipo" if product.stock > 0 else "Imeisha"

        return CON, (
            f"{product.name}\n"
            f"Bei: TSh "
            f"{int(product.price):,}/"
            f"{product.unit}\n"
            f"Stock: {product.stock} "
            f"{product.unit} ({stock_status})\n"
            "Tafuta bidhaa wapi?\n"
            f"1. Eneo langu"
            f"{' (' + farmer_district + ')' if farmer_district else ''}\n"
            f"2. Mkoa wangu"
            f"{' (' + farmer_region + ')' if farmer_region else ''}\n"
            "3. Tafuta mkoa/wilaya nyingine\n"
            "99. Tanzania nzima\n"
            "0. Rudi"
        )


    # ======================================================================
    # ORDER LOCATION CHOICE
    # ======================================================================

    def _handle_order_location_choice(
        self,
        full_text: str,
        last_input: str
    ):
        """
        Decide where to search for suppliers.
        """

        if last_input == "0":

            self._goto("order_product")

            return CON, (
                self._render_order_product()
            )

        # ---------------------------------------------------------------
        # FARMER DISTRICT
        # ---------------------------------------------------------------

        if last_input == "1":

            farmer_district = (
                self.data.get(
                    "farmer_district",
                    ""
                )
                or ""
            ).strip()

            if not farmer_district:

                self._goto(
                    "order_search_location"
                )

                return CON, (
                    "Eneo lako halijajulikani.\n"
                    "Andika mkoa au wilaya:"
                )

            self.data[
                "search_location_type"
            ] = "district"

            self.data[
                "search_location"
            ] = farmer_district

            return self._show_product_suppliers(
                farmer_district,
                "district"
            )

        # ---------------------------------------------------------------
        # FARMER REGION
        # ---------------------------------------------------------------

        if last_input == "2":

            farmer_region = (
                self.data.get(
                    "farmer_region",
                    ""
                )
                or ""
            ).strip()

            if not farmer_region:

                self._goto(
                    "order_search_location"
                )

                return CON, (
                    "Mkoa wako haujulikani.\n"
                    "Andika jina la mkoa:"
                )

            self.data[
                "search_location_type"
            ] = "region"

            self.data[
                "search_location"
            ] = farmer_region

            return self._show_product_suppliers(
                farmer_region,
                "region"
            )

        # ---------------------------------------------------------------
        # SEARCH OTHER LOCATION
        # ---------------------------------------------------------------

        if last_input == "3":

            self._goto(
                "order_search_location"
            )

            return CON, (
                "TAFUTA ENEO\n"
                "Andika jina la mkoa au wilaya.\n\n"
                "Mfano:\n"
                "Morogoro\n"
                "Arusha\n"
                "Dodoma\n\n"
                "Andika eneo:"
            )

        # ---------------------------------------------------------------
        # ALL TANZANIA
        # ---------------------------------------------------------------

        if last_input == "99":

            self.data[
                "search_location_type"
            ] = "all"

            self.data[
                "search_location"
            ] = ""

            return self._show_product_suppliers(
                "",
                "all"
            )

        return CON, (
            _error() +
            "\nChagua 1, 2, 3 au 99:"
        )


    # ======================================================================
    # SEARCH LOCATION
    # ======================================================================

    def _handle_order_search_location(
        self,
        full_text: str,
        last_input: str
    ):
        """
        Search supplier by region/district.
        """

        search_term = (
            last_input or ""
        ).strip()

        if len(search_term) < 2:

            return CON, (
                "Andika jina la mkoa au wilaya "
                "(angalau herufi 2):"
            )

        self.data[
            "search_location"
        ] = search_term

        self.data[
            "search_location_type"
        ] = "search"

        return self._show_product_suppliers(
            search_term,
            "search"
        )


    # ======================================================================
    # FIND SUPPLIERS FOR SELECTED PRODUCT - ILIYOREKEBISHWA KABISA
    # ======================================================================

    def _show_product_suppliers(
        self,
        search_term="",
        location_type="all"
    ):
        """
        Find suppliers based on LOCATION FIRST, then check products.

        IMPORTANT:
        - Kwanza tafuta suppliers katika eneo (district/region)
        - Kisha angalia kama wana bidhaa (IPO, IMEISHA, au KWA OMBI)
        - Hii inahakikisha suppliers wote katika eneo wanaonekana

        Priority:
            1. Same district (Wilaya)
            2. Same region (Mkoa)
            3. Other regions
        """

        product_id = self.data.get(
            "product_id"
        )

        if not product_id:
            self._goto("order_product")
            return CON, self._render_order_product()

        try:
            selected_product = (
                Product.objects
                .select_related("category", "supplier")
                .get(id=product_id, is_available=True)
            )
        except Product.DoesNotExist:
            self._goto("order_category")
            return CON, self._render_order_category()

        # ==============================================================
        # STEP 1: GET FARMER LOCATION
        # ==============================================================
        
        farmer_district = (
            self.data.get("farmer_district", "") or ""
        ).strip()
        
        farmer_region = (
            self.data.get("farmer_region", "") or ""
        ).strip()

        # ==============================================================
        # STEP 2: GET ALL SUPPLIERS IN LOCATION (Kwanza eneo)
        # ==============================================================

        # Tafuta suppliers wote waliosajiliwa
        all_suppliers = list(
            Supplier.objects.filter(
                is_active=True
            ).distinct()
        )

        # ==============================================================
        # STEP 3: FILTER SUPPLIERS BY LOCATION (District/Region)
        # ==============================================================

        def normalize_text(value):
            return (value or "").strip().lower()

        def supplier_matches_location(supplier, target_text, location_kind):
            supplier_region = normalize_text(supplier.region)
            supplier_district = normalize_text(supplier.district)
            supplier_location = normalize_text(supplier.location)
            supplier_ward = normalize_text(supplier.ward)
            supplier_village = normalize_text(supplier.village)
            target = normalize_text(target_text)

            if not target:
                return False

            candidate_values = [
                supplier_region,
                supplier_district,
                supplier_location,
                supplier_ward,
                supplier_village,
            ]

            if location_kind == "district":
                return any(target in value for value in candidate_values)

            if location_kind == "region":
                return supplier_region == target or target in supplier_region or (
                    supplier_location and target in supplier_location
                )

            if location_kind == "search":
                return any(target in value for value in candidate_values)

            return True

        def filter_by_location(suppliers):
            """Filter suppliers by district or region with safe fallback to location text."""
            if not suppliers:
                return []

            filtered = []
            search = (search_term or "").strip().lower()

            for supplier in suppliers:
                if location_type == "district":
                    if supplier_matches_location(supplier, farmer_district, "district"):
                        filtered.append(supplier)

                elif location_type == "region":
                    if supplier_matches_location(supplier, farmer_region, "region"):
                        filtered.append(supplier)

                elif location_type == "search":
                    if supplier_matches_location(supplier, search, "search"):
                        filtered.append(supplier)

                else:
                    filtered.append(supplier)

            return filtered

        # Apply location filter to all suppliers
        suppliers_in_location = filter_by_location(all_suppliers)

        # ==============================================================
        # STEP 4: IF NO SUPPLIERS IN LOCATION, SHOW ERROR
        # ==============================================================

        if not suppliers_in_location:
            self._goto("order_location_choice")
            
            location_text = f"katika {search_term}" if search_term else "katika eneo hili"
            
            return CON, (
                f"Hakuna muuzaji {location_text}.\n\n"
                "1. Tafuta eneo lingine\n"
                "2. Tanzania nzima\n"
                "3. Chagua bidhaa nyingine\n"
                "0. Rudi"
            )

        # ==============================================================
        # STEP 5: PRIORITIZE SUPPLIERS BY LOCATION
        # ==============================================================

        district_suppliers = []
        region_suppliers = []
        other_suppliers = []

        for supplier in suppliers_in_location:
            supplier_district = (supplier.district or "").lower()
            supplier_region = (supplier.region or "").lower()
            supplier_location = (supplier.location or "").lower()
            supplier_ward = (supplier.ward or "").lower()
            supplier_village = (supplier.village or "").lower()

            same_district = (
                bool(farmer_district)
                and (
                    farmer_district.lower() in supplier_district
                    or
                    farmer_district.lower() in supplier_location
                    or
                    farmer_district.lower() in supplier_ward
                    or
                    farmer_district.lower() in supplier_village
                )
            )

            same_region = (
                bool(farmer_region)
                and (
                    farmer_region.lower() in supplier_region
                    or
                    farmer_region.lower() in supplier_location
                )
            )

            if same_district:
                district_suppliers.append(supplier)
            elif same_region:
                region_suppliers.append(supplier)
            else:
                other_suppliers.append(supplier)

        # ==============================================================
        # STEP 6: BUILD FINAL LIST (MAX 9)
        # ==============================================================

        all_suppliers = district_suppliers + region_suppliers + other_suppliers

        # Remove duplicates
        unique_suppliers = []
        seen_ids = set()
        
        for supplier in all_suppliers:
            if supplier.id not in seen_ids:
                seen_ids.add(supplier.id)
                unique_suppliers.append(supplier)
        
        # Deduplicate repeated supplier names so the menu stays clean.
        deduped_suppliers = []
        seen_names = set()
        for supplier in unique_suppliers:
            key = (supplier.company_name or "").strip().lower()
            if not key or key in seen_names:
                continue
            seen_names.add(key)
            deduped_suppliers.append(supplier)

        all_suppliers = deduped_suppliers[:9]

        if not all_suppliers:
            self._goto("order_location_choice")

            location_text = f"katika {search_term}" if search_term else "katika eneo hili"

            return CON, (
                f"Hakuna muuzaji {location_text}.\n"
                "Tafuta eneo lingine.\n\n"
                "1. Tafuta eneo lingine\n"
                "2. Tanzania nzima\n"
                "3. Chagua bidhaa nyingine\n"
                "0. Rudi"
            )

        # ==============================================================
        # STEP 7: SAVE SUPPLIERS
        # ==============================================================

        self.data["supplier_ids"] = [
            str(supplier.id)
            for supplier in all_suppliers
        ]

        self.data["supplier_search_location"] = search_term
        self.data["supplier_location_type"] = location_type

        self._goto("order_supplier")

        # ==============================================================
        # STEP 8: CHECK PRODUCT AVAILABILITY FOR EACH SUPPLIER
        # ==============================================================

        lines = []
        valid_supplier_ids = []

        # Check if ANY supplier has the product in stock
        any_has_stock = False
        any_has_product = False

        for supplier in all_suppliers:
            # Check if supplier has this product
            supplier_product = (
                Product.objects.filter(
                    supplier=supplier,
                    id=selected_product.id,
                    is_available=True
                )
                .first()
            )
            
            if supplier_product and supplier_product.stock > 0:
                any_has_stock = True
                any_has_product = True
            elif supplier_product:
                any_has_product = True

        # ==============================================================
        # STEP 9: BUILD MENU
        # ==============================================================

        for supplier in all_suppliers:

            # Check if supplier has the product
            supplier_product = (
                Product.objects.filter(
                    supplier=supplier,
                    id=selected_product.id,
                    is_available=True
                )
                .first()
            )

            has_stock = supplier_product and supplier_product.stock > 0
            has_product = supplier_product is not None

            valid_supplier_ids.append(str(supplier.id))

            supplier_region = supplier.region or ""
            supplier_district = supplier.district or ""
            supplier_location = supplier.location or ""

            # ----------------------------------------------------------
            # LOCATION LABEL
            # ----------------------------------------------------------

            if (
                farmer_district
                and (
                    farmer_district.lower() in supplier_district.lower()
                    or
                    farmer_district.lower() in supplier_location.lower()
                )
            ):
                location_note = "Wilaya yako"

            elif (
                farmer_region
                and
                farmer_region.lower() in supplier_region.lower()
            ):
                location_note = "Mkoa wako"

            else:
                location_note = supplier_region or "Mkoa mwingine"

            location = (
                getattr(supplier, "location_summary", None)
                or supplier.location
                or supplier.district
                or supplier.region
                or "Eneo halijatajwa"
            )

            # ----------------------------------------------------------
            # PRODUCT AVAILABILITY STATUS
            # ----------------------------------------------------------

            if has_product and has_stock:
                price_display = f"TSh {int(supplier_product.price):,}/{supplier_product.unit}"
                stock_display = f"Stock: {supplier_product.stock} {supplier_product.unit}"
                status_marker = ""
                status_text = "IPO"

            elif has_product and not has_stock:
                price_display = f"TSh {int(supplier_product.price):,}/{supplier_product.unit}"
                stock_display = "Imeisha stock"
                status_marker = ""
                status_text = "IMEISHA"

            else:
                price_display = "Kwa Ombi"
                stock_display = "Wasiliana na muuzaji"
                status_marker = ""
                status_text = "KWA OMBI"

            status_label = "Status: " + status_text
            if has_product and has_stock:
                price_label = f"Bei: {price_display}"
            elif has_product and not has_stock:
                price_label = f"Bei: {price_display}"
            else:
                price_label = "Bei: Kwa ombi"

            lines.append(
                f"{len(valid_supplier_ids)}. {supplier.company_name}\n"
                f"   {status_label}\n"
                f"   {price_label}\n"
                f"   Eneo: {location}\n"
                f"   {location_note}"
            )

        # ==============================================================
        # STEP 10: UPDATE SUPPLIER IDS
        # ==============================================================

        self.data["supplier_ids"] = valid_supplier_ids

        # ==============================================================
        # STEP 11: EXTRA OPTIONS
        # ==============================================================

        lines.append("")
        lines.append("00. Tafuta mkoa/wilaya nyingine")
        lines.append("99. Tanzania nzima")
        lines.append("0. Rudi")

        # ==============================================================
        # STEP 12: LOCATION TITLE
        # ==============================================================

        if location_type == "district":
            location_title = f"Wilaya: {search_term}"
        elif location_type == "region":
            location_title = f"Mkoa: {search_term}"
        elif location_type == "search":
            location_title = f"Eneo: {search_term}"
        else:
            location_title = "Tanzania"

        # ==============================================================
        # STEP 13: ADD NOTE IF PRODUCT NOT AVAILABLE
        # ==============================================================

        note = ""
        if not any_has_stock and any_has_product:
            note = "\nBidhaa imeisha stock kwa wauzaji wote."
        elif not any_has_product:
            note = "\nHawapo kabisa."

        # ==============================================================
        # STEP 14: SHOW HOW MANY SUPPLIERS FOUND
        # ==============================================================

        supplier_count = len(valid_supplier_ids)

        return CON, _menu(
            f"{selected_product.name}{note}\n"
            f"{location_title} | Wauzaji: {supplier_count}\n"
            "Wauzaji wanaopatikana:",
            lines
        )


    # ======================================================================
    # SUPPLIER / OFFER SELECTION
    # ======================================================================

    def _handle_order_supplier(
        self,
        full_text: str,
        last_input: str
    ):
        """
        Select supplier for selected product.
        """

        # ---------------------------------------------------------------
        # SEARCH ANOTHER LOCATION
        # ---------------------------------------------------------------

        if last_input == "00":

            self._goto(
                "order_search_location"
            )

            return CON, (
                "TAFUTA ENEO\n"
                "Andika mkoa au wilaya:\n"
                "Mfano: Arusha\n"
                "Mfano: Dodoma\n"
                "Mfano: Morogoro\n\n"
                "Andika eneo:"
            )

        # ---------------------------------------------------------------
        # ALL TANZANIA
        # ---------------------------------------------------------------

        if last_input == "99":

            self.data[
                "search_location_type"
            ] = "all"

            self.data[
                "search_location"
            ] = ""

            return self._show_product_suppliers(
                "",
                "all"
            )

        # ---------------------------------------------------------------
        # BACK
        # ---------------------------------------------------------------

        if last_input == "0":

            self._goto(
                "order_location_choice"
            )

            return CON, (
                f"{self.data.get('product_name', 'Bidhaa')}\n"
                "Tafuta bidhaa wapi?\n"
                "1. Eneo langu\n"
                "2. Mkoa wangu\n"
                "3. Tafuta mkoa/wilaya nyingine\n"
                "99. Tanzania nzima\n"
                "0. Rudi"
            )

        # ---------------------------------------------------------------
        # SELECT SUPPLIER
        # ---------------------------------------------------------------

        idx = _parse_int(last_input)

        if idx is None or idx < 1:

            return CON, (
                _error() +
                "\nChagua namba sahihi ya muuzaji:"
            )

        try:

            supplier_id = self.data[
                "supplier_ids"
            ][idx - 1]

        except (
            IndexError,
            KeyError
        ):

            return CON, (
                _error() +
                "\nChagua namba sahihi ya muuzaji:"
            )

        try:

            supplier = Supplier.objects.get(
                id=supplier_id,
                is_active=True
            )

        except Supplier.DoesNotExist:

            return CON, (
                "Samahani, muuzaji huyu "
                "hapatikani.\n"
                "Chagua muuzaji mwingine."
            )

        # ---------------------------------------------------------------
        # GET SELECTED PRODUCT
        # ---------------------------------------------------------------

        product_id = self.data.get(
            "product_id"
        )

        try:

            product = (
                Product.objects
                .select_related(
                    "supplier",
                    "category"
                )
                .get(
                    id=product_id,
                    supplier=supplier,
                    is_available=True
                )
            )

            has_product = True
            product_exists = True

        except Product.DoesNotExist:

            # Supplier doesn't have this product
            has_product = False
            product_exists = False
            product = None

        # ---------------------------------------------------------------
        # IF PRODUCT NOT AVAILABLE - OFFER "KWA OMBI"
        # ---------------------------------------------------------------

        if not has_product or product.stock <= 0:

            # Save supplier info for manual order
            self.data["supplier_id"] = str(supplier.id)
            self.data["supplier_name"] = supplier.company_name
            self.data["supplier_phone"] = supplier.phone or ""
            
            self._end()
            
            if not product_exists:
                return END, (
                    f"{self.data.get('product_name', 'Bidhaa')}\n"
                    f"Muuzaji: {supplier.company_name}\n"
                    f"Simu: {supplier.phone or 'Hajapatikana'}\n"
                    f"Mahali: {supplier.location_summary or supplier.location or supplier.district or supplier.region or 'Eneo'}\n"
                    "Bidhaa hii haipo kwenye orodha ya muuzaji.\n\n"
                    "Wasiliana naye moja kwa moja\n"
                    "kupanga ununuzi.\n\n"
                    f"Simu: {supplier.phone or 'Hajapatikana'}\n"
                    "Piga *566# tena."
                )
            else:
                return END, (
                    f"{self.data.get('product_name', 'Bidhaa')}\n"
                    f"Muuzaji: {supplier.company_name}\n"
                    f"Simu: {supplier.phone or 'Hajapatikana'}\n"
                    f"Mahali: {supplier.location_summary or supplier.location or supplier.district or supplier.region or 'Eneo'}\n"
                    "Bidhaa imeisha stock.\n\n"
                    "Wasiliana naye moja kwa moja\n"
                    "kupanga ununuzi.\n\n"
                    f"Simu: {supplier.phone or 'Hajapatikana'}\n"
                    "Piga *566# tena."
                )

        # ---------------------------------------------------------------
        # SAVE SUPPLIER
        # ---------------------------------------------------------------

        self.data["supplier_id"] = (
            str(supplier.id)
        )

        self.data["supplier_name"] = (
            supplier.company_name
        )

        self.data["supplier_phone"] = (
            supplier.phone or ""
        )

        # ---------------------------------------------------------------
        # SAVE PRODUCT
        # ---------------------------------------------------------------

        self.data["product_id"] = (
            str(product.id)
        )

        self.data["product_name"] = (
            product.name
        )

        self.data["product_unit"] = (
            product.unit
        )

        self.data["product_stock"] = (
            product.stock
        )

        self.data["product_price"] = (
            str(product.price)
        )

        # ---------------------------------------------------------------
        # ASK QUANTITY
        # ---------------------------------------------------------------

        self._goto(
            "order_quantity"
        )

        return CON, (
            f"{product.name}\n"
            f"Muuzaji: "
            f"{supplier.company_name}\n"
            f"Bei: TSh "
            f"{int(product.price):,}/"
            f"{product.unit}\n"
            f"Stock: {product.stock} "
            f"{product.unit}\n"
            "Weka kiasi:"
        )


    # ======================================================================
    # QUANTITY
    # ======================================================================

    def _handle_order_quantity(
        self,
        full_text: str,
        last_input: str
    ):
        """
        Validate quantity.
        """

        qty = _parse_int(
            last_input
        )

        if qty is None or qty <= 0:

            return CON, (
                "Weka kiasi sahihi.\n"
                "Mfano: 10"
            )

        available_stock = int(
            self.data.get(
                "product_stock",
                0
            )
        )

        if qty > available_stock:

            return CON, (
                f"Samahani, stock iliyopo ni "
                f"{available_stock} "
                f"{self.data.get('product_unit', '')} tu.\n"
                "Weka kiasi kingine:"
            )

        self.data[
            "quantity"
        ] = qty

        # ---------------------------------------------------------------
        # GET FARMER
        # ---------------------------------------------------------------

        farmer = Farmer.objects.filter(
            phone_number=self.phone_number
        ).first()

        if not farmer:

            self._end()

            return END, (
                "Tafadhali jisajili kwanza."
            )

        # ---------------------------------------------------------------
        # SAVED FARMER ADDRESS
        # ---------------------------------------------------------------

        if (
            farmer.village
            or farmer.district
            or farmer.region
        ):

            self.data[
                "_farmer_village"
            ] = farmer.village or ""

            self.data[
                "_farmer_district"
            ] = farmer.district or ""

            self.data[
                "_farmer_region"
            ] = farmer.region or ""

            self._goto(
                "order_address_choice"
            )

            saved_location = ", ".join(
                value
                for value in [
                    farmer.village,
                    farmer.district,
                    farmer.region
                ]
                if value
            )

            return CON, (
                "ANWANI YA KUFIKISHA\n"
                f"{saved_location}\n"
                "1. Tumia anwani hii\n"
                "2. Badilisha anwani"
            )

        # ---------------------------------------------------------------
        # NO ADDRESS
        # ---------------------------------------------------------------

        self._goto(
            "order_village"
        )

        return CON, (
            "Andika kijiji/eneo "
            "la kufikisha:"
        )


    # ======================================================================
    # ADDRESS CHOICE
    # ======================================================================

    def _handle_order_address_choice(
        self,
        full_text: str,
        last_input: str
    ):
        """
        Use saved farmer address or enter new address.
        """

        if last_input == "1":

            self.data["village"] = (
                self.data.get(
                    "_farmer_village",
                    ""
                )
            )

            self.data["district"] = (
                self.data.get(
                    "_farmer_district",
                    ""
                )
            )

            self.data["region"] = (
                self.data.get(
                    "_farmer_region",
                    ""
                )
            )

            return self._show_order_confirm()

        if last_input == "2":

            self._goto(
                "order_village"
            )

            return CON, (
                "Andika kijiji/eneo "
                "la kufikisha:"
            )

        return CON, (
            _error() +
            "\nChagua 1 au 2:"
        )


    # ======================================================================
    # VILLAGE
    # ======================================================================

    def _handle_order_village(
        self,
        full_text: str,
        last_input: str
    ):
        value = (
            last_input or ""
        ).strip()

        if len(value) < 2:

            return CON, (
                "Andika kijiji/eneo sahihi:"
            )

        self.data[
            "village"
        ] = value

        self._goto(
            "order_district"
        )

        return CON, (
            "Andika wilaya "
            "ya kufikisha:"
        )


    # ======================================================================
    # DISTRICT
    # ======================================================================

    def _handle_order_district(
        self,
        full_text: str,
        last_input: str
    ):
        value = (
            last_input or ""
        ).strip()

        if len(value) < 2:

            return CON, (
                "Andika wilaya:"
            )

        self.data[
            "district"
        ] = value

        self._goto(
            "order_region"
        )

        return CON, (
            "Andika mkoa "
            "wa kufikisha:"
        )


    # ======================================================================
    # REGION
    # ======================================================================

    def _handle_order_region(
        self,
        full_text: str,
        last_input: str
    ):
        value = (
            last_input or ""
        ).strip()

        if len(value) < 2:

            return CON, (
                "Andika mkoa:"
            )

        self.data[
            "region"
        ] = value

        return self._show_order_confirm()


    # ======================================================================
    # ORDER CONFIRMATION
    # ======================================================================

    def _show_order_confirm(self):

        d = self.data

        try:

            quantity = int(
                d.get(
                    "quantity",
                    0
                )
            )

            price = Decimal(
                str(
                    d.get(
                        "product_price",
                        "0"
                    )
                )
            )

        except (
            TypeError,
            ValueError
        ):

            self._end()

            return END, (
                "Samahani, taarifa za "
                "agizo si sahihi."
            )

        if quantity <= 0 or price < 0:

            self._end()

            return END, (
                "Samahani, taarifa za "
                "agizo si sahihi."
            )

        total = (
            quantity * price
        )

        self._goto(
            "order_confirm"
        )

        delivery_parts = [
            d.get("village", ""),
            d.get("district", ""),
            d.get("region", "")
        ]

        delivery_address = ", ".join(
            part.strip()
            for part in delivery_parts
            if part and part.strip()
        )

        return CON, (
            "THIBITISHA ODA\n"
            f"Bidhaa: "
            f"{d.get('product_name', '')}\n"
            f"Kiasi: {quantity} "
            f"{d.get('product_unit', '')}\n"
            f"Bei: TSh "
            f"{int(price):,}/"
            f"{d.get('product_unit', '')}\n"
            f"Jumla: TSh "
            f"{int(total):,}\n"
            f"Muuzaji: "
            f"{d.get('supplier_name', '')}\n"
            f"Simu: "
            f"{d.get('supplier_phone', '')}\n"
            f"Fikisha: "
            f"{delivery_address}\n"
            "1. Thibitisha\n"
            "2. Badilisha\n"
            "3. Ghairi"
        )


    # ======================================================================
    # FINAL ORDER CONFIRMATION
    # ======================================================================

    def _handle_order_confirm(
        self,
        full_text: str,
        last_input: str
    ):
        """
        Create final order.

        Uses select_for_update() so two farmers
        cannot buy the same last stock simultaneously.
        """

        # ---------------------------------------------------------------
        # CANCEL
        # ---------------------------------------------------------------

        if last_input == "3":

            self._end()

            return END, (
                "Agizo limeghairiwa."
            )

        # ---------------------------------------------------------------
        # CHANGE
        # ---------------------------------------------------------------

        if last_input == "2":

            self._goto(
                "order_quantity"
            )

            return CON, (
                self._render_order_quantity()
            )

        # ---------------------------------------------------------------
        # INVALID
        # ---------------------------------------------------------------

        if last_input != "1":

            return CON, (
                _error() +
                "\nChagua 1, 2 au 3:"
            )

        # ---------------------------------------------------------------
        # GET FARMER
        # ---------------------------------------------------------------

        farmer = Farmer.objects.filter(
            phone_number=self.phone_number
        ).first()

        if not farmer:

            self._end()

            return END, (
                "Tafadhali jisajili kwanza."
            )

        d = self.data

        product_id = d.get(
            "product_id"
        )

        supplier_id = d.get(
            "supplier_id"
        )

        if not product_id:

            self._end()

            return END, (
                "Samahani, bidhaa "
                "haijapatikana."
            )

        if not supplier_id:

            self._end()

            return END, (
                "Samahani, muuzaji "
                "hajapatikana."
            )

        # ---------------------------------------------------------------
        # QUANTITY
        # ---------------------------------------------------------------

        try:

            quantity = int(
                d.get(
                    "quantity",
                    0
                )
            )

        except (
            TypeError,
            ValueError
        ):

            quantity = 0

        if quantity <= 0:

            self._end()

            return END, (
                "Kiasi cha bidhaa "
                "si sahihi."
            )

        # ---------------------------------------------------------------
        # TRANSACTION
        # ---------------------------------------------------------------

        try:

            from django.db import transaction

            with transaction.atomic():

                # ========================================================
                # LOCK PRODUCT
                # ========================================================

                product = (
                    Product.objects
                    .select_for_update()
                    .select_related(
                        "supplier",
                        "category"
                    )
                    .get(
                        id=product_id,
                        supplier_id=supplier_id,
                        is_available=True
                    )
                )

                # ========================================================
                # VERIFY SUPPLIER
                # ========================================================

                supplier = product.supplier

                if not supplier:

                    raise ValueError(
                        "Product has no supplier."
                    )

                if not supplier.is_active:

                    raise ValueError(
                        "Supplier is inactive."
                    )

                if supplier.is_verified != "VERIFIED":

                    raise ValueError(
                        "Supplier is not verified."
                    )

                # ========================================================
                # CHECK STOCK AGAIN
                # ========================================================

                if product.stock < quantity:

                    self._end()

                    return END, (
                        "Samahani, stock "
                        "imebadilika.\n"
                        f"Stock iliyopo sasa ni "
                        f"{product.stock} "
                        f"{product.unit} tu."
                    )

                # ========================================================
                # TOTAL
                # ========================================================

                total_amount = (
                    product.price
                    * quantity
                )

                # ========================================================
                # DELIVERY ADDRESS
                # ========================================================

                delivery_parts = [
                    d.get("village", ""),
                    d.get("district", ""),
                    d.get("region", "")
                ]

                delivery_address = ", ".join(
                    part.strip()
                    for part in delivery_parts
                    if part
                    and part.strip()
                )

                if not delivery_address:

                    self._end()

                    return END, (
                        "Samahani, anwani "
                        "ya kufikisha haipo."
                    )

                # ========================================================
                # CREATE ORDER
                # ========================================================

                order = Order.objects.create(
                    farmer=farmer,
                    supplier=supplier,
                    total_amount=total_amount,
                    delivery_address=delivery_address,
                    status="PENDING"
                )

                # ========================================================
                # CREATE ORDER ITEM
                # ========================================================

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    price=product.price
                )

                # ========================================================
                # REDUCE STOCK
                # ========================================================

                product.stock -= quantity

                product.save(
                    update_fields=[
                        "stock"
                    ]
                )

                # ========================================================
                # SEND SMS
                # ========================================================

                self._send_order_notifications(
                    order=order,
                    farmer=farmer,
                    supplier=supplier,
                    product_name=product.name,
                    quantity=quantity,
                    product_unit=product.unit,
                    total_amount=total_amount
                )

            # ============================================================
            # END SESSION
            # ============================================================

            self._end()

            return END, (
                "ODA IMEPOKELEWA!\n"
                f"{product.name} x{quantity}\n"
                f"Jumla: TSh "
                f"{int(total_amount):,}\n"
                f"Ref: #{order.reference}\n"
                f"Muuzaji: "
                f"{supplier.company_name}\n"
                f"Simu: "
                f"{supplier.phone or ''}\n"
                f"Fikisha: "
                f"{delivery_address}\n"
                "SMS imetumwa kwako "
                "na kwa muuzaji.\n\n"
                "Asante kutumia "
                "Lunyili AgroSmart."
            )

        except Product.DoesNotExist:

            self._end()

            return END, (
                "Samahani, bidhaa "
                "haipatikani au "
                "imeondolewa."
            )

        except ValueError as exc:

            self.logger.warning(
                f"Order validation error: {exc}"
            )

            self._end()

            return END, (
                "Samahani, muuzaji "
                "hapatikani au "
                "hajaruhusiwa kuuza "
                "bidhaa hii."
            )

        except Exception as exc:

            self.logger.exception(
                f"Order creation error: {exc}"
            )

            self._end()

            return END, (
                "Samahani, agizo "
                "halikufanikiwa.\n"
                "Jaribu tena baadaye."
            )


    # ======================================================================
    # ORDER SMS NOTIFICATIONS
    # ======================================================================

    def _send_order_notifications(
        self,
        order,
        farmer,
        supplier,
        product_name,
        quantity,
        product_unit,
        total_amount
    ):
        """
        Farmer SMS:
            - Order reference
            - Product
            - Quantity
            - Total
            - Supplier
            - Supplier phone
            - Delivery address

        Supplier SMS:
            - Order reference
            - Farmer name
            - Farmer phone
            - Product
            - Quantity
            - Total
            - Delivery address
        """

        try:

            # ==============================================================
            # SMS TO FARMER
            # ==============================================================

            if (
                farmer
                and farmer.phone_number
            ):

                farmer_message = (
                    "Lunyili AgroSmart\n"
                    f"Oda #{order.reference} "
                    "imepokelewa.\n"
                    f"{product_name} x{quantity} "
                    f"{product_unit}.\n"
                    f"Jumla: TSh "
                    f"{int(total_amount):,}.\n"
                    f"Muuzaji: "
                    f"{supplier.company_name}.\n"
                    f"Simu ya muuzaji: "
                    f"{supplier.phone or '-'}.\n"
                    f"Fikisha: "
                    f"{order.delivery_address}.\n"
                    "Subiri uthibitisho "
                    "wa muuzaji."
                )

                self._send_sms(
                    farmer.phone_number,
                    farmer_message
                )

            # ==============================================================
            # SMS TO SUPPLIER
            # ==============================================================

            if (
                supplier
                and supplier.phone
            ):

                farmer_name = (
                    getattr(
                        farmer,
                        "full_name",
                        None
                    )
                    or getattr(
                        farmer,
                        "name",
                        None
                    )
                    or "Mkulima"
                )

                supplier_message = (
                    "Lunyili AgroSmart\n"
                    f"ODA MPYA #{order.reference}\n"
                    f"Mkulima: "
                    f"{farmer_name}.\n"
                    f"Simu: "
                    f"{farmer.phone_number}.\n"
                    f"Bidhaa: "
                    f"{product_name}.\n"
                    f"Kiasi: {quantity} "
                    f"{product_unit}.\n"
                    f"Jumla: TSh "
                    f"{int(total_amount):,}.\n"
                    f"Fikisha: "
                    f"{order.delivery_address}.\n"
                    "Tafadhali wasiliana "
                    "na mkulima "
                    "kuthibitisha oda."
                )

                self._send_sms(
                    supplier.phone,
                    supplier_message
                )

            return True

        except Exception as exc:

            self.logger.exception(
                "Error sending order notifications: "
                f"{exc}"
            )

            return False


    # ======================================================================
    # RENDER METHODS FOR ORDER
    # ======================================================================

    def _render_order_category(self) -> str:

        category_ids = self.data.get(
            "category_ids",
            []
        )

        lines = []

        for index, category_id in enumerate(
            category_ids[:9],
            1
        ):

            try:

                category = Category.objects.get(
                    id=category_id,
                    is_active=True
                )

                lines.append(
                    f"{index}. {category.name}"
                )

            except Category.DoesNotExist:

                continue

        lines.append(
            "0. Rudi Menu"
        )

        return _menu(
            "AGIZA PEMBEJEO\n"
            "Chagua kundi la bidhaa:",
            lines
        )


    def _render_order_product(self) -> str:

        product_ids = self.data.get(
            "product_ids",
            []
        )

        lines = []

        for index, product_id in enumerate(
            product_ids[:9],
            1
        ):

            try:

                product = Product.objects.get(
                    id=product_id,
                    is_available=True
                )

                if product.stock <= 0:
                    continue

                lines.append(
                    f"{index}. {product.name}\n"
                    f"   TSh "
                    f"{int(product.price):,}/"
                    f"{product.unit}\n"
                    f"   Stock: "
                    f"{product.stock}"
                )

            except Product.DoesNotExist:

                continue

        lines.append(
            "0. Rudi Makundi"
        )

        return _menu(
            self.data.get(
                "category_name",
                "Bidhaa"
            ),
            lines
        )


    def _render_order_quantity(self) -> str:

        try:

            price = Decimal(
                str(
                    self.data.get(
                        "product_price",
                        "0"
                    )
                )
            )

        except (
            TypeError,
            ValueError
        ):

            price = Decimal("0")

        return (
            f"{self.data.get('product_name', 'Bidhaa')}\n"
            f"Muuzaji: "
            f"{self.data.get('supplier_name', '')}\n"
            f"Bei: TSh "
            f"{int(price):,}/"
            f"{self.data.get('product_unit', '')}\n"
            f"Stock: "
            f"{self.data.get('product_stock', 0)} "
            f"{self.data.get('product_unit', '')}\n"
            "Weka kiasi:"
        )


    def _render_order_confirm(self) -> str:

        d = self.data

        try:

            quantity = int(
                d.get(
                    "quantity",
                    0
                )
            )

            price = Decimal(
                str(
                    d.get(
                        "product_price",
                        "0"
                    )
                )
            )

        except (
            TypeError,
            ValueError
        ):

            quantity = 0
            price = Decimal("0")

        total = (
            quantity * price
        )

        delivery_address = ", ".join(
            part.strip()
            for part in [
                d.get("village", ""),
                d.get("district", ""),
                d.get("region", "")
            ]
            if part
            and part.strip()
        )

        return (
            "THIBITISHA ODA\n"
            f"Bidhaa: "
            f"{d.get('product_name', '')}\n"
            f"Kiasi: {quantity} "
            f"{d.get('product_unit', '')}\n"
            f"Bei: TSh "
            f"{int(price):,}/"
            f"{d.get('product_unit', '')}\n"
            f"Jumla: TSh "
            f"{int(total):,}\n"
            f"Muuzaji: "
            f"{d.get('supplier_name', '')}\n"
            f"Simu: "
            f"{d.get('supplier_phone', '')}\n"
            f"Fikisha: "
            f"{delivery_address}\n"
            "1. Thibitisha\n"
            "2. Badilisha\n"
            "3. Ghairi"
        )

    # ======================================================================
    # 3. CROP PRICES - FROM DATABASE
    # ======================================================================
    def _start_prices(self):
        """Show market prices from database"""
        latest_date = MarketPrice.objects.order_by('-price_date').values_list('price_date', flat=True).first()
        
        if latest_date:
            prices = list(MarketPrice.objects.filter(price_date=latest_date).order_by('crop')[:10])
        else:
            prices = list(MarketPrice.objects.all().order_by('-price_date', 'crop')[:10])
        
        if not prices:
            self._end()
            return END, (
                "Samahani, hakuna taarifa za bei kwa sasa.\n"
                "Piga *566# tena baadaye."
            )
        
        lines = []
        for p in prices:
            market = p.market or "Soko"
            unit = p.unit or "kg"
            lines.append(f"{p.crop}: TSh {int(p.price):,}/{unit} ({market})")
        
        self._end()
        return END, (
            "Bei za Soko:\n" + 
            "\n".join(lines[:10]) + 
            f"\n\nTarehe: {latest_date or timezone.now().date()}\n"
            "Piga *566# tena."
        )

    # ======================================================================
    # 4. FIND BUYERS - KUUZA MAZAO (SELL CROPS)
    # ======================================================================
    def _start_buyers(self):
        """Start buyer search - find buyers for crops"""
        
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza (chagua 1 kwenye menu kuu)."
        
        # Use all known crop names from market prices and active buying requests,
        # not only the farmer's current primary crop. That allows the farmer to
        # choose the crop they want to sell at that moment.
        crop_candidates = list(MarketPrice.objects.values_list('crop', flat=True).distinct())
        crop_candidates += list(BuyingRequest.objects.filter(is_open=True, expiry_date__gte=timezone.now().date()).values_list('crop', flat=True).distinct())

        farmer_crop = Farmer.objects.filter(phone_number=self.phone_number).values_list('primary_crop', flat=True).first()
        if farmer_crop:
            crop_candidates.append(farmer_crop)

        crops = []
        seen_crops = set()
        for crop in crop_candidates:
            name = (crop or '').strip()
            if not name or name.lower() in seen_crops:
                continue
            seen_crops.add(name.lower())
            crops.append(name)

        if not crops:
            crops = ["Mahindi", "Mpunga", "Maharage", "Viazi", "Nyanya", "Mtama", "Alizeti", "Kunde", "Njugu"]
        else:
            crops = sorted(crops, key=lambda x: x.lower())[:9]
        
        self.data["crops"] = crops
        self._goto("buyer_crop")
        
        lines = [f"{i+1}. {c}" for i, c in enumerate(crops[:9])]
        lines.append("0. Rudi Menu")
        
        return CON, _menu(
            "Kuuza Mazao\n"
            "Chagua zao unalouza:",
            lines
        )

    def _handle_buyer_crop(self, full_text: str, last_input: str):
        """Handle crop selection for selling and ask the user for the region to search."""

        if last_input == "0":
            self._goto("main", keep_data=False)
            return CON, screen_main_menu()

        idx = _parse_int(last_input)
        if idx is None or idx < 1:
            return CON, _error() + "\nChagua namba sahihi ya zao:"
        idx -= 1

        try:
            crop = self.data["crops"][idx]
        except (IndexError, KeyError):
            return CON, _error() + "\nChagua namba sahihi ya zao:"

        self.data["selected_crop"] = crop
        self._goto("buyer_search_region")

        default_region = ""
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if farmer:
            default_region = farmer.region or ""

        if default_region:
            return CON, (
                f"Tafuta wanunuzi wa {crop}\n"
                f"Mkoa wako: {default_region}\n\n"
                "Andika mkoa au wilaya unayotaka kuuza kwa hiyo zao:\n"
                "Mfano: Morogoro, Mvomero, Dar es Salaam\n\n"
                "Mkoa/Wilaya:"
            )

        return CON, (
            f"Tafuta wanunuzi wa {crop}\n"
            "Andika mkoa au wilaya unayotaka kuuza kwa hiyo zao:\n"
            "Mfano: Morogoro, Mvomero, Dar es Salaam\n\n"
            "Mkoa/Wilaya:"
        )

    def _handle_buyer_select(self, full_text: str, last_input: str):
        """Handle buyer selection"""
        
        if last_input == "0":
            self._goto("buyer_crop")
            return self._render_buyer_crop()
        
        if last_input == "00":
            self._goto("buyer_search_region")
            return CON, (
                "Tafuta Mnunuzi\n"
                "Andika mkoa au wilaya\n"
                "unayotaka kuuza mazao:\n"
                "(Mfano: Dar es Salaam, Arusha)\n"
                "Jina la Mkoa/Wilaya:"
            )
        
        idx = _parse_int(last_input)
        if idx is None or idx < 1:
            return CON, _error() + "\nChagua namba sahihi ya mnunuzi:"
        idx -= 1
        
        try:
            buyer_id = self.data["buyer_ids"][idx]
        except (IndexError, KeyError):
            return CON, _error() + "\nChagua namba sahihi ya mnunuzi:"
        
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza."
        
        crop = self.data.get("selected_crop", "")
        self.data["selected_buyer_id"] = buyer_id
        
        try:
            buying_request = BuyingRequest.objects.get(id=buyer_id)
            buyer_name = buying_request.buyer.company_name if buying_request.buyer and buying_request.buyer.company_name else "Mnunuzi"
            buyer_phone = buying_request.buyer.phone if buying_request.buyer else "0712345678"
            buyer_price = f"TSh {int(buying_request.price_offered):,}/kg"
            buyer_location = buying_request.location or "Eneo"
        except BuyingRequest.DoesNotExist:
            return CON, _error() + "\nMnunuzi hapatikani. Jaribu tena."
        
        self.data["selected_buyer_name"] = buyer_name
        self.data["selected_buyer_phone"] = buyer_phone
        self.data["selected_buyer_price"] = buyer_price
        self.data["selected_buyer_location"] = buyer_location
        
        self._goto("buyer_confirm")
        return CON, self._render_buyer_confirm()

    def _handle_buyer_search_region(self, full_text: str, last_input: str):
        """Search for buyers by region/district and show crop-specific buyers with prices."""

        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika jina la mkoa au wilaya (herufi 2 au zaidi):"

        search_term = last_input.strip()
        crop = self.data.get("selected_crop", "")

        buyers = list(BuyingRequest.objects.filter(
            crop__icontains=crop,
            location__icontains=search_term,
            is_open=True,
            expiry_date__gte=timezone.now().date()
        ).order_by('-created_at')[:9])

        if not buyers:
            buyers = list(BuyingRequest.objects.filter(
                crop__icontains=crop,
                is_open=True,
                expiry_date__gte=timezone.now().date()
            ).order_by('-created_at')[:5])

        if not buyers:
            return CON, (
                f"Hawapo kabisa.\n"
                f"Hakuna wanunuzi wa {crop} katika '{search_term}'.\n\n"
                "Andika mkoa mwingine:"
            )

        self.data["buyer_ids"] = [str(b.id) for b in buyers]
        self.data["nearby_buyer_count"] = 0
        self._goto("buyer_select")

        lines = []
        for i, b in enumerate(buyers, 1):
            buyer_name = b.buyer.company_name if b.buyer and b.buyer.company_name else "Mnunuzi"
            lines.append(
                f"{i}. {buyer_name}\n"
                f"   {b.crop}\n"
                f"   Kiasi: {b.quantity_kg}kg\n"
                f"   Bei: TSh {int(b.price_offered):,}/kg\n"
                f"   Eneo: {b.location}"
            )

        lines.append("0. Rudi Menu")

        return CON, _menu(
            f"Wanunuzi wa {crop}\n"
            f"Mkoa/Wilaya: {search_term}\n"
            "",
            lines
        )

    def _handle_buyer_confirm(self, full_text: str, last_input: str):
        """Handle final buyer confirmation"""
        
        if last_input == '2':
            self._goto("buyer_select")
            return self._render_buyer_select()
        
        if last_input != '1':
            return CON, _error() + "\nChagua 1 kuthibitisha au 2 kughairi:"
        
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza."
        
        buyer_name = self.data.get("selected_buyer_name", "Mnunuzi")
        buyer_phone = self.data.get("selected_buyer_phone", "0712345678")
        buyer_price = self.data.get("selected_buyer_price", "")
        crop = self.data.get("selected_crop", "")
        buyer_id = self.data.get("selected_buyer_id")
        
        # Save interest
        try:
            buying_request = BuyingRequest.objects.get(id=buyer_id)
            InterestedFarmer.objects.get_or_create(
                buying_request=buying_request,
                farmer=farmer
            )
        except BuyingRequest.DoesNotExist:
            pass
        
        # Send SMS to farmer
        farmer_message = (
            f"Umefanikiwa kuonyesha nia ya kuuza {crop}!\n"
            f"Mnunuzi: {buyer_name}\n"
            f"Simu: {buyer_phone}\n"
            f"Bei: {buyer_price}\n"
            f"Watawasiliana nawe hivi karibuni."
        )
        self._send_sms(farmer.phone_number, farmer_message)
        
        # Send SMS to buyer
        if buyer_phone:
            buyer_message = (
                f"Mkulima ameonyesha nia ya kuuza {crop}!\n"
                f"Jina: {farmer.full_name}\n"
                f"Simu: {farmer.phone_number}\n"
                f"Eneo: {farmer.location_summary}\n"
                f"Wasiliana naye moja kwa moja."
            )
            self._send_sms(buyer_phone, buyer_message)
        
        self._end()
        return END, (
            f" Taarifa zimewasilishwa!\n"
            f"SMS imetumwa kwako na kwa mnunuzi.\n"
            f"Mnunuzi: {buyer_name}\n"
            f"Simu: {buyer_phone}\n"
            f"Bei: {buyer_price}\n"
            f"Wasiliana naye moja kwa moja\n"
            f"kupanga mauzo.\n"
            f"Piga *566# tena."
        )

    # ======================================================================
    # RENDER METHODS FOR BUYERS
    # ======================================================================

    def _render_buyer_crop(self) -> str:
        """Re-render crop selection for buyers"""
        crops = self.data.get("crops", [])
        lines = [f"{i+1}. {c}" for i, c in enumerate(crops[:9])]
        lines.append("0. Rudi Menu")
        return _menu("Kuuza Mazao\nChagua zao unalouza:", lines)

    def _render_buyer_select(self) -> str:
        """Re-render buyer selection"""
        crop = self.data.get("selected_crop", "")
        buyers = self.data.get("buyer_ids", [])
        lines = []
        for i, _ in enumerate(buyers, 1):
            lines.append(f"{i}. Mnunuzi {i}")
        lines.append("00. Tafuta Wanunuzi Mkoa Mwingine")
        lines.append("0. Rudi Menu")
        return _menu(f"Wanunuzi wa {crop}:", lines)

    def _render_buyer_confirm(self) -> str:
        """Re-render buyer confirmation"""
        return (
            f"Thibitisha Mnunuzi\n"
            f"{self.data.get('selected_buyer_name', '')}\n"
            f"Simu: {self.data.get('selected_buyer_phone', '')}\n"
            f"Mahali: {self.data.get('selected_buyer_location', '')}\n"
            f"{self.data.get('selected_crop', '')}: {self.data.get('selected_buyer_price', '')}\n"
            f"1. Thibitisha\n"
            f"2. Ghairi"
        )

    # ======================================================================
    # 5. FARMING ADVICE
    # ======================================================================
    def _start_advice(self):
        self._goto("advice")
        return CON, _menu("Ushauri wa Kilimo", [
            "1. Ushauri wa Jumla",
            "2. Udhibiti wa Wadudu",
            "3. Udhibiti wa Magonjwa",
            "4. Mbolea na Rutuba",
            "5. Rudi Menu"
        ])

    def _handle_advice(self, full_text: str, last_input: str):
        category_map = {
            '1': 'GENERAL',
            '2': 'PEST',
            '3': 'DISEASE',
            '4': 'FERTILIZER',
        }
        
        if last_input == '5':
            self._goto('main')
            return CON, screen_main_menu()
        
        if last_input in category_map:
            advice = Advice.objects.filter(
                category=category_map[last_input],
                is_published=True
            ).order_by('-published_date').first()
            
            if advice:
                self._end()
                return END, f"{advice.title}\n{advice.content[:300]}\n\nPiga *566# tena."
        
        default_msgs = {
            '1': "Ushauri wa Jumla:\n- Panda wakati wa mvua\n- Tumia mbegu bora\n- Palilia mara kwa mara\n- Vuna kwa wakati",
            '2': "Udhibiti wa Wadudu:\n- Tumia dawa asilia\n- Panda mazao mchanganyiko\n- Angalia shamba mara kwa mara",
            '3': "Udhibiti wa Magonjwa:\n- Tumia mbegu zilizothibitishwa\n- Weka umbali sahihi wa kupanda\n- Ondoa mimea mgonjwa",
            '4': "Mbolea na Rutuba:\n- Tumia mbolea ya samadi\n- Weka mazao mbadala\n- Jaribu udongo mara kwa mara",
        }
        
        if last_input in default_msgs:
            self._end()
            return END, f"{default_msgs[last_input]}\n\nPiga *566# tena."
        
        return CON, _error()

    # ======================================================================
    # 6. WEATHER - WITH GPS AND PLACE NAME SUPPORT
    # ======================================================================

    def _start_weather(self):
        """Start weather with simple options for farmers"""
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        
        menu = "HALI YA HEWA\n\n"
        menu += "Chagua njia:\n\n"
        menu += "1. Eneo Langu (GPS)\n"
        menu += "2. Jina la Eneo\n"
        menu += "3. Mkoa\n"
        menu += "0. Rudi Nyuma\n\n"
        menu += "Chagua: 0-3"
        
        self._goto("weather_method")
        return CON, menu

    def _handle_weather_method(self, full_text: str, last_input: str):
        """Handle weather method selection"""
        if last_input == '0':
            self._goto('main')
            return CON, screen_main_menu()
        
        if last_input == '1':
            return self._handle_weather_gps()
        
        if last_input == '2':
            self._goto("weather_place")
            return CON, (
                "HALI YA HEWA\n\n"
                "Andika jina la kijiji au mji wako:\n"
                "(Mfano: Morogoro, Dakawa, Mvomero)\n\n"
                "Jina la Eneo:"
            )
        
        if last_input == '3':
            self._goto("weather_region")
            return CON, "Andika mkoa wako (mfano: Morogoro):"
        
        return CON, _error() + "\nChagua 1, 2, au 3:"

    def _handle_weather_gps(self):
        """Handle GPS - find location by phone number"""
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        
        if farmer:
            if farmer.latitude and farmer.longitude:
                return self._show_weather_by_coordinates(
                    float(farmer.latitude), 
                    float(farmer.longitude),
                    farmer.village or "Eneo lako"
                )
            
            if farmer.village:
                from .location_service import LocationService
                location = LocationService()
                lat, lon = location.get_coordinates_by_place(farmer.village)
                if lat and lon:
                    farmer.latitude = lat
                    farmer.longitude = lon
                    farmer.save()
                    return self._show_weather_by_coordinates(lat, lon, farmer.village)
            
            if farmer.district:
                from .location_service import LocationService
                location = LocationService()
                lat, lon = location.get_coordinates_by_place(farmer.district)
                if lat and lon:
                    return self._show_weather_by_coordinates(lat, lon, farmer.district)
            
            if farmer.region:
                from .location_service import LocationService
                location = LocationService()
                lat, lon = location.get_coordinates_by_place(farmer.region)
                if lat and lon:
                    return self._show_weather_by_coordinates(lat, lon, farmer.region)
        
        self._goto("weather_place")
        return CON, (
            "HATUA YA 1\n\n"
            "Tumeshindwa kupata eneo lako.\n"
            "Tafadhali andika jina la kijiji au mji wako:\n"
            "(Mfano: Morogoro, Dakawa, Mvomero)\n\n"
            "Jina la Eneo:"
        )

    def _handle_weather_place(self, full_text: str, last_input: str):
        """Handle weather by place name"""
        if not last_input or len(last_input.strip()) < 2:
            return CON, "HATUA YA 1\n\nAndika jina halali (herufi 2 au zaidi):"
        
        place_name = last_input.strip()
        
        try:
            from .location_service import LocationService
            location = LocationService()
            lat, lon = location.get_coordinates_by_place(place_name)
            
            if lat and lon:
                farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
                if farmer:
                    farmer.latitude = lat
                    farmer.longitude = lon
                    farmer.village = place_name
                    farmer.save()
                
                return self._show_weather_by_coordinates(lat, lon, place_name)
            else:
                return self._show_weather_by_region(place_name)
        except Exception as e:
            self.logger.error(f"Weather place error: {str(e)}")
            return CON, f"Samahani, '{place_name}' haijapatikana.\nJaribu tena:"

    def _handle_weather_region(self, full_text: str, last_input: str):
        """Handle weather by region name"""
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika mkoa wako (mfano: Morogoro):"
        
        region = last_input.strip()
        return self._show_weather_by_region(region)

    def _show_weather_by_coordinates(self, lat, lon, place_name):
        """Show weather using coordinates - no default data"""
        try:
            from .weather_service import WeatherService
            weather = WeatherService()
            data = weather.get_weather_by_coordinates(lat, lon)
            
            if data and data.get('temperature') is not None:
                self._end()
                return END, self._format_weather_response(data, place_name)
            else:
                self._end()
                return END, (
                    "HALI YA HEWA\n"
                    "Samahani, hakuna taarifa\n"
                    "za hali ya hewa kwa sasa.\n"
                    "Jaribu tena baadaye.\n\n"
                    "Dial *566# tena."
                )
        except Exception as e:
            self.logger.error(f"Weather coordinates error: {str(e)}")
            self._end()
            return END, (
                "HALI YA HEWA\n"
                "Samahani, kuna tatizo.\n"
                "Jaribu tena baadaye.\n"
                "Dial *566# tena."
            )

    def _show_weather_by_region(self, region: str):
        """Show weather by region name - no default data"""
        self._end()
        
        try:
            from ..models import WeatherData
            weather = WeatherData.objects.filter(region__icontains=region).order_by('-fetched_at').first()
            if weather and weather.temperature is not None:
                return END, self._format_weather_from_db(weather, region)
            else:
                return END, (
                    "HALI YA HEWA\n"
                    "Samahani, hakuna taarifa\n"
                    "za hali ya hewa kwa sasa.\n"
                    "Jaribu tena baadaye.\n\n"
                    "Dial *566# tena."
                )
        except Exception as e:
            self.logger.error(f"Weather region error: {str(e)}")
            return END, (
                "HALI YA HEWA\n"
                "Samahani, kuna tatizo.\n"
                "Jaribu tena baadaye.\n"
                "Dial *566# tena."
            )

    def _format_weather_response(self, data, place_name):
        """Format weather data nicely without emojis"""
        
        if not data:
            return (
                "HALI YA HEWA\n"
                "Samahani, hakuna taarifa\n"
                "za hali ya hewa kwa sasa.\n"
                "Jaribu tena baadaye.\n\n"
                "Dial *566# tena."
            )
        
        temp = data.get('temperature')
        humidity = data.get('humidity')
        wind = data.get('wind_speed')
        description = data.get('weather_description')
        city = data.get('city', place_name)
        
        if temp is None:
            return (
                "HALI YA HEWA\n"
                "Samahani, hakuna taarifa\n"
                "za hali ya hewa kwa sasa.\n"
                "Jaribu tena baadaye.\n\n"
                "Dial *566# tena."
            )
        
        desc_sw = self._translate_weather_description(description or 'Anga safi')
        current_time = timezone.now().strftime('%d/%m/%Y %H:%M')
        
        output = (
            "HALI YA HEWA\n"
            f"Eneo: {city}\n"
            f"Joto: {temp:.1f}°C\n"
            f"Unyevu: {humidity:.0f}%\n"
            f"Upepo: {wind:.1f} m/s\n"
            f"Hali: {desc_sw}\n"
            f"Imesasishwa: {current_time}\n\n"
            "Dial *566# tena."
        )
        
        return output

    def _format_weather_from_db(self, weather, region):
        """Format weather data from database"""
        output = (
            "HALI YA HEWA\n"
            f"Eneo: {region}\n"
            f"Joto: {weather.temperature}°C\n"
            f"Unyevu: {weather.humidity}%\n"
            f"Hali: {weather.condition}\n"
            f"Imesasishwa: {weather.fetched_at.strftime('%d/%m/%Y %H:%M')}\n\n"
            "Dial *566# tena."
        )
        return output

    def _translate_weather_description(self, description):
        """Translate weather description to Swahili"""
        if not description:
            return "Anga safi"
        
        desc_lower = description.lower()
        
        translations = {
            'clear sky': 'Anga safi',
            'few clouds': 'Mawingu machache',
            'scattered clouds': 'Mawingu yaliyotawanyika',
            'broken clouds': 'Mawingu yaliyovunjika',
            'overcast clouds': 'Mawingu mengi',
            'partly cloudy': 'Mawingu kiasi',
            'cloudy': 'Mawingu',
            'rain': 'Mvua',
            'light rain': 'Mvua kidogo',
            'moderate rain': 'Mvua ya wastani',
            'heavy rain': 'Mvua kubwa',
            'shower rain': 'Mvua ya mawe',
            'thunderstorm': 'Dhoruba ya radi',
            'snow': 'Theluji',
            'mist': 'Ukungu',
            'fog': 'Ukungu mzito',
            'haze': 'Vumbi hewani',
            'smoke': 'Moshi',
            'dust': 'Vumbi',
            'sand': 'Mchanga',
            'ash': 'Mavumbi',
            'squall': 'Dhoruba',
            'tornado': 'Kimbunga',
            'sunny': 'Jua kali',
            'fair': 'Anga safi',
            'hot': 'Joto kali',
            'cold': 'Baridi',
            'windy': 'Upepo mkali',
            'humid': 'Unyevu mkali',
            'drizzle': 'Mvua nyepesi',
            'showers': 'Mvua ya mawe',
            'storm': 'Dhoruba',
            'blizzard': 'Dhoruba ya theluji',
            'freezing': 'Baridi kali',
            'icy': 'Barafu',
            'frost': 'Baridi',
        }
        
        for key, value in translations.items():
            if key in desc_lower:
                return value
        
        return description.capitalize()

    # ======================================================================
    # RENDER METHODS FOR WEATHER
    # ======================================================================

    def _render_weather_method(self) -> str:
        menu = "HALI YA HEWA\n\n"
        menu += "Chagua njia:\n\n"
        menu += "1. Eneo Langu (GPS)\n"
        menu += "2. Jina la Eneo\n"
        menu += "3. Mkoa\n"
        menu += "0. Rudi Nyuma\n\n"
        menu += "Chagua: 0-3"
        return menu

    def _render_weather_place(self) -> str:
        return (
            "HALI YA HEWA\n\n"
            "Andika jina la mji wako:\n"
            "(Mfano: Morogoro, Dakawa, Mvomero)\n\n"
            "Jina la Eneo:"
        )

    def _render_weather_region(self) -> str:
        return "Andika mkoa wako (mfano: Morogoro):"

# ======================================================================
# 7. FINANCIAL SERVICES 
# ======================================================================

    def _start_financial(self):
        """Start financial services"""
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza (chagua 1 kwenye menu kuu)."
        
        if not farmer.full_name:
            self._end()
            return END, "Tafadhali kamilisha usajili wako kwanza."
        
        farmer.update_profile_completeness()
        
        self._goto("financial_menu")
        return CON, (
            "HUDUMA ZA KIFEDHA\n"
            "====================\n"
            f"Kamilisho: {farmer.profile_completeness}%\n"
            "====================\n"
            "1. Omba Mkopo\n"
            "2. Angalia Hali ya Mkopo\n"
            "3. Historia ya Mikopo\n"
            "4. Alama Yangu\n"
            "5. Kamilisha Taarifa\n"
            "6. Mikopo Ninayostahili\n"
            "7. Kubali Mkopo Ulioidhinishwa\n"
            "8. Ratiba ya Marejesho\n"
            "9. Lipa Mkopo (USSD Push)\n"
            "0. Rudi Menu"
        )


    def _handle_financial_menu(self, full_text: str, last_input: str):
        """Handle financial menu"""
        if last_input == '0':
            self._goto('main')
            return CON, screen_main_menu()
        
        if last_input == '1':
            return self._start_loan_application()
        
        if last_input == '2':
            return self._check_loan_status()
        
        if last_input == '3':
            return self._check_loan_history()
        
        if last_input == '4':
            return self._check_my_score()
        
        if last_input == '5':
            return self._start_profile_completion()
        
        if last_input == '6':
            return self._show_eligible_loans()

        if last_input == '7':
            return self._show_loan_acceptance()

        if last_input == '8':
            return self._show_repayment_schedule()

        if last_input == '9':
            return self._start_repayment_push()
        
        return CON, _error() + "\nChagua 0-9:"


    def _start_repayment_push(self):
        """Start repayment via USSD push"""
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza."
        
        loan = Loan.objects.filter(
            application__farmer=farmer,
            status__in=[LoanStatus.DISBURSED, LoanStatus.ACTIVE, LoanStatus.PARTIALLY_REPAID, LoanStatus.OVERDUE]
        ).order_by('-disbursed_at').first()
        
        if not loan:
            self._end()
            return END, "Huna mkopo unaoendelea."
        
        # Check if there's a due repayment
        repayment = loan.repayments.filter(
            status__in=[RepaymentStatus.DUE, RepaymentStatus.OVERDUE, RepaymentStatus.PARTIALLY_PAID]
        ).order_by('installment_number').first()
        
        if not repayment:
            self._end()
            return END, "Hakuna malipo yanayodaiwa kwa sasa."
        
        self.data['repayment_loan_id'] = str(loan.id)
        self.data['repayment_id'] = str(repayment.id)
        self.data['repayment_amount'] = str(repayment.remaining_balance)
        self.data['installment_number'] = str(repayment.installment_number)
        
        self._goto("financial_repayment_confirm")
        
        return CON, (
            f"MALIPO YA MKOPO\n"
            f"====================\n"
            f"Kipindi #{repayment.installment_number}\n"
            f"Kiasi: TSh {int(repayment.remaining_balance):,}\n"
            f"Tarehe ya mwisho: {repayment.due_date.strftime('%d/%m/%Y')}\n"
            f"====================\n"
            f"1. Lipa kwa USSD Push\n"
            f"2. Lipa kwa Mwongozo\n"
            f"0. Rudi"
        )


    def _handle_financial_repayment_confirm(self, full_text: str, last_input: str):
        """Handle repayment confirmation"""
        if last_input == '0':
            self._goto('financial_menu')
            return CON, self._render_financial_menu()
        
        if last_input == '2':
            # Manual payment - show instructions
            self._end()
            return END, (
                f"MALIPO YA MWONGOZO\n"
                f"====================\n"
                f"Kipindi #{self.data.get('installment_number', 'N/A')}\n"
                f"Kiasi: TSh {self.data.get('repayment_amount', '0')}\n"
                f"====================\n"
                f"Wasiliana na taasisi yako ya fedha\n"
                f"kwa maelezo ya malipo.\n\n"
                f"Piga *566# tena baada ya malipo."
            )
        
        if last_input != '1':
            return CON, "Chagua 1 au 2:"
        
        # Process USSD push
        try:
            loan = Loan.objects.get(id=self.data.get('repayment_loan_id'))
            from .services.repayment_service import initiate_repayment_via_ussd
            
            payment, message = initiate_repayment_via_ussd(loan)
            
            if payment and payment.status == PaymentTransactionStatus.PENDING:
                self._end()
                return END, (
                    f"✅ OMBI LA MALIPO LIMETUMWA!\n"
                    f"====================\n"
                    f"Kiasi: TSh {int(payment.amount):,}\n"
                    f"Ref: {payment.provider_reference[:8]}\n"
                    f"====================\n"
                    f"Utapokea mwaliko wa malipo\n"
                    f"kwenye simu yako.\n\n"
                    f"Thibitisha malipo ili kukamilisha."
                )
            else:
                self._end()
                return END, f"Samahani: {message}"
                
        except Exception as e:
            logger.exception(f"Repayment push error: {str(e)}")
            self._end()
            return END, "Samahani, kuna tatizo. Jaribu tena baadaye."


    def _start_loan_application(self):
        """Start loan application - with loan type selection"""
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza."
        
        # Update score
        farmer.calculate_credit_readiness()
        
        self._goto("financial_loan_type")
        return CON, (
            "CHAGUA AINA YA MKOPO\n"
            "====================\n"
            "1. Mkopo wa Pembejeo\n"
            "   (Mbolea, Mbegu, Dawa)\n"
            "2. Mkopo wa Uzalishaji\n"
            "3. Mkopo wa Biashara ya Mazao\n"
            "0. Rudi"
        )


    def _handle_financial_loan_type(self, full_text: str, last_input: str):
        """Handle loan type selection"""
        if last_input == '0':
            self._goto('financial_menu')
            return CON, self._render_financial_menu()
        
        loan_types = {
            '1': 'INPUT',
            '2': 'PRODUCTION',
            '3': 'MARKET',
        }
        
        if last_input not in loan_types:
            return CON, _error() + "\nChagua 1, 2 au 3:"
        
        self.data['loan_type'] = loan_types[last_input]
        
        if last_input == '1':
            return self._start_input_loan()
        else:
            return self._show_loan_products()


    def _start_input_loan(self):
        """Start input loan - farmer selects inputs"""
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()

        products = LoanProduct.objects.filter(
            is_active=True,
            loan_type='INPUT',
        ).order_by('name')[:9]
        if not products:
            return END, "Samahani, hakuna bidhaa za mkopo wa pembejeo kwa sasa."

        self.data['input_loan_products'] = [str(product.id) for product in products]
        self._goto("financial_input_loan_product")
        lines = [
            f"{index}. {product.name} (TSh {int(product.min_amount):,}-{int(product.max_amount):,})"
            for index, product in enumerate(products, 1)
        ]
        lines.append("0. Rudi")
        return CON, _menu("CHAGUA BIDHAA YA MKOPO", lines)

    def _handle_financial_input_loan_product(self, full_text: str, last_input: str):
        if last_input == '0':
            self._goto('financial_loan_type')
            return CON, self._render_financial_loan_type()

        index = _parse_int(last_input)
        product_ids = self.data.get('input_loan_products', [])
        if not index or index > len(product_ids):
            return CON, "Chagua namba sahihi ya bidhaa ya mkopo:"

        try:
            product = LoanProduct.objects.get(id=product_ids[index - 1], is_active=True, loan_type='INPUT')
        except LoanProduct.DoesNotExist:
            return CON, "Bidhaa ya mkopo haipo. Chagua tena:"

        self.data['selected_product_id'] = str(product.id)
        self.data['selected_product_name'] = product.name
        self.data['selected_product_min'] = str(product.min_amount)
        self.data['selected_product_max'] = str(product.max_amount)
        self.data['selected_product_interest'] = str(product.interest_rate)
        self.data['selected_product_duration'] = str(product.duration_months)
        return self._show_input_categories()

    def _show_input_categories(self):
        """Show available input categories after the loan product is fixed."""
        categories = Category.objects.filter(is_active=True)[:5]
        if not categories:
            return END, "Samahani, hakuna bidhaa kwa sasa."
        
        self.data['input_category_ids'] = [str(c.id) for c in categories]
        self._goto("financial_input_category")
        
        lines = [f"{i+1}. {c.name}" for i, c in enumerate(categories)]
        lines.append("0. Rudi")
        return CON, _menu(
            "CHAGUA PEMBEJEO\n"
            "====================\n"
            "Chagua aina ya pembejeo:",
            lines
        )


    def _handle_financial_input_category(self, full_text: str, last_input: str):
        """Handle input category selection"""
        if last_input == '0':
            self._goto('financial_loan_type')
            return CON, self._render_financial_loan_type()
        
        idx = _parse_int(last_input)
        if not idx or idx < 1:
            return CON, "Chagua namba sahihi:"
        
        try:
            cat_id = self.data['input_category_ids'][idx - 1]
            category = Category.objects.get(id=cat_id)
        except:
            return CON, "Kundi halipo. Chagua tena:"
        
        products = Product.objects.filter(
            category=category,
            is_available=True,
            stock__gt=0
        )[:9]
        
        if not products:
            return CON, f"Hakuna bidhaa katika {category.name}.\nChagua kundi lingine:"
        
        self.data['input_product_ids'] = [str(p.id) for p in products]
        self._goto("financial_input_product")
        
        lines = []
        for i, p in enumerate(products):
            lines.append(
                f"{i+1}. {p.name}\n"
                f"   TSh {int(p.price):,}/{p.unit}"
            )
        lines.append("0. Rudi")
        return CON, _menu(
            f"{category.name}\n"
            "Chagua bidhaa:",
            lines
        )


    def _handle_financial_input_product(self, full_text: str, last_input: str):
        """Handle input product selection"""
        if last_input == '0':
            self._goto('financial_input_category')
            return CON, self._render_financial_input_category()
        
        idx = _parse_int(last_input)
        if not idx or idx < 1:
            return CON, "Chagua namba sahihi:"
        
        try:
            product_id = self.data['input_product_ids'][idx - 1]
            product = Product.objects.select_related('supplier').get(id=product_id)
        except:
            return CON, "Bidhaa haipo. Chagua tena:"
        
        self.data['input_product_id'] = str(product.id)
        self.data['input_product_name'] = product.name
        self.data['input_product_price'] = str(product.price)
        self.data['input_product_unit'] = product.unit
        self.data['input_supplier_id'] = str(product.supplier.id)
        self.data['input_supplier_name'] = product.supplier.company_name
        
        self._goto("financial_input_quantity")
        return CON, (
            f"{product.name}\n"
            f"====================\n"
            f"Muuzaji: {product.supplier.company_name}\n"
            f"Bei: TSh {int(product.price):,}/{product.unit}\n"
            f"====================\n"
            f"Weka kiasi unachotaka:"
        )


    def _handle_financial_input_quantity(self, full_text: str, last_input: str):
        """Handle input quantity"""
        qty = _parse_int(last_input)
        if not qty or qty <= 0:
            return CON, "Weka kiasi sahihi:"
        
        price = Decimal(self.data['input_product_price'])
        total = qty * price
        
        self.data['input_quantity'] = qty
        self.data['loan_amount'] = str(total)

        loan_product_id = self.data.get('selected_product_id')
        loan_product = LoanProduct.objects.filter(id=loan_product_id, is_active=True).first()
        if not loan_product:
            return CON, "Bidhaa ya mkopo haipatikani. Rudi uanze tena:"
        if total < loan_product.min_amount or total > loan_product.max_amount:
            return CON, (
                f"Kiasi lazima kiwe kati ya TSh {int(loan_product.min_amount):,} "
                f"na TSh {int(loan_product.max_amount):,}. Weka kiasi kingine:"
            )
        
        self._goto("financial_purpose")
        return CON, (
            f"Bidhaa: {self.data['input_product_name']}\n"
            f"Kiasi: {qty} {self.data['input_product_unit']}\n"
            f"Jumla: TSh {int(total):,}\n"
            f"====================\n"
            f"Weka sababu ya mkopo:"
        )


    def _show_loan_products(self):
        """Show loan products for non-input loans"""
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        
        products = LoanProduct.objects.filter(is_active=True)[:9]
        if not products:
            self._end()
            return END, "Hakuna bidhaa za mkopo kwa sasa."
        
        self.data["loan_products"] = []
        for p in products:
            self.data["loan_products"].append({
                'id': str(p.id),
                'name': p.name,
                'interest': str(p.interest_rate),
                'min': str(p.min_amount),
                'max': str(p.max_amount),
                'duration': str(p.duration_months)
            })
        
        self._goto("financial_products")
        lines = []
        for i, p in enumerate(products[:9], 1):
            lines.append(
                f"{i}. {p.name}\n"
                f"   Riba: {p.interest_rate}% | Muda: {p.duration_months}m"
            )
        lines.append("0. Rudi")
        
        if farmer:
            lines.append(f"⭐ Alama yako: {farmer.credit_readiness_score}/100")
        
        return CON, _menu(
            "BIDHAA ZA MKOPO\n"
            "====================\n"
            "Chagua bidhaa:",
            lines
        )


    def _handle_financial_products(self, full_text: str, last_input: str):
        """Handle loan product selection"""
        if last_input == '0':
            self._goto('financial_loan_type')
            return CON, self._render_financial_loan_type()
        
        idx = _parse_int(last_input)
        if idx is None or idx < 1:
            return CON, _error() + "\nChagua namba sahihi ya bidhaa:"
        idx -= 1
        
        try:
            product_data = self.data["loan_products"][idx]
        except (IndexError, KeyError):
            return CON, _error() + "\nChagua namba sahihi ya bidhaa:"
        
        self.data["selected_product_id"] = product_data['id']
        self.data["selected_product_name"] = product_data['name']
        self.data["selected_product_min"] = product_data['min']
        self.data["selected_product_max"] = product_data['max']
        self.data["selected_product_interest"] = product_data['interest']
        self.data["selected_product_duration"] = product_data['duration']
        
        self._goto("financial_amount")
        return CON, (
            f"{self.data['selected_product_name']}\n"
            f"====================\n"
            f"Riba: {self.data['selected_product_interest']}%\n"
            f"Muda: {self.data['selected_product_duration']} miezi\n"
            f"Kiwango: TSh {int(Decimal(self.data['selected_product_min'])):,} - {int(Decimal(self.data['selected_product_max'])):,}\n"
            f"====================\n"
            f"Weka kiasi unachotaka (TSh):"
        )


    def _handle_financial_amount(self, full_text: str, last_input: str):
        """Handle loan amount input"""
        amount = _parse_decimal(last_input)
        if amount is None or amount <= 0:
            return CON, "Andika kiasi sahihi (mfano: 1000000):"
        
        min_amount = Decimal(self.data["selected_product_min"])
        max_amount = Decimal(self.data["selected_product_max"])
        
        if amount < min_amount:
            return CON, f"Kiasi cha chini ni TSh {int(min_amount):,}. Weka kiasi kingine:"
        
        if amount > max_amount:
            return CON, f"Kiasi cha juu ni TSh {int(max_amount):,}. Weka kiasi kingine:"
        
        self.data["loan_amount"] = str(amount)
        self._goto("financial_purpose")
        return CON, (
            f"Kiasi: TSh {int(amount):,}\n"
            f"====================\n"
            f"Weka sababu ya mkopo\n"
            f"(mfano: Kununua pembejeo):"
        )


    def _handle_financial_purpose(self, full_text: str, last_input: str):
        """Handle loan purpose input"""
        if not last_input or len(last_input.strip()) < 3:
            return CON, "Andika sababu ya mkopo (herufi 3 au zaidi):"
        
        self.data["loan_purpose"] = last_input.strip()
        self._goto("financial_confirm")
        
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        eligibility = farmer.get_eligibility_level() if farmer else None
        
        return CON, (
            f"THIBITISHA OMBI LA MKOPO\n"
            f"====================\n"
            f"Bidhaa: {self.data['selected_product_name']}\n"
            f"Kiasi: TSh {int(Decimal(self.data['loan_amount'])):,}\n"
            f"Sababu: {self.data['loan_purpose']}\n"
            f"====================\n"
            f"⭐ Alama yako: {farmer.credit_readiness_score}/100\n"
            f"📊 Hali: {eligibility['label'] if eligibility else 'Inaangaliwa'}\n"
            f"====================\n"
            f"1. Thibitisha\n"
            f"2. Ghairi"
        )


    def _handle_financial_confirm(self, full_text: str, last_input: str):
        """Handle final loan confirmation"""
        if last_input == '2':
            self._goto('financial_menu')
            return CON, self._render_financial_menu()
        
        if last_input != '1':
            return CON, _error() + "\nChagua 1 kuthibitisha au 2 kughairi:"
        
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza."
        
        try:
            selected_loan_product = LoanProduct.objects.get(
                id=self.data['selected_product_id'], is_active=True
            )
        except (KeyError, LoanProduct.DoesNotExist):
            self._end()
            return END, "Samahani, bidhaa ya mkopo haipatikani."

        if farmer.credit_readiness_score < selected_loan_product.minimum_credit_score:
            self._end()
            return END, (
                f"Samahani, bado haustahili mkopo.\n"
                f"Alama yako: {farmer.credit_readiness_score}/100.\n"
                f"Bidhaa hii inahitaji alama {selected_loan_product.minimum_credit_score}/100.\n\n"
                "Endelea kuagiza na kukamilisha\n"
                "taarifa zako."
            )
        
        try:
            # Check if input loan
            if self.data.get('input_product_id'):
                return self._create_input_loan(farmer)
            else:
                return self._create_cash_loan(farmer)
            
        except Exception as e:
            self.logger.error(f"Loan application error: {str(e)}")
            self._end()
            return END, "Samahani, ombi halikufanikiwa. Jaribu tena."


    def _create_input_loan(self, farmer):
        """Create a pending financing request and unpaid supplier order."""
        product_id = self.data.get('input_product_id')
        quantity = int(self.data.get('input_quantity', 0))
        amount = Decimal(self.data.get('loan_amount', '0'))
        purpose = self.data.get('loan_purpose', 'Kununua pembejeo')
        
        with transaction.atomic():
            product = Product.objects.select_for_update().select_related('supplier').get(id=product_id)
            if product.stock < quantity or not product.is_available:
                raise ValueError("Insufficient input stock")
            supplier = product.supplier
            loan_product = LoanProduct.objects.get(
                id=self.data['selected_product_id'], is_active=True, loan_type='INPUT'
            )
            if LoanApplication.objects.filter(
                farmer=farmer,
                loan_product=loan_product,
                status__in=['PENDING', 'UNDER_REVIEW', 'INFO_REQUIRED', 'APPROVED'],
            ).exists():
                raise ValueError("Duplicate active application")

            order = Order.objects.create(
                farmer=farmer,
                supplier=supplier,
                total_amount=amount,
                quantity_unit=product.unit,
                delivery_address=f"{farmer.village}, {farmer.district}",
                status='LOAN_PENDING',
                payment_status='PENDING',
            )
            OrderItem.objects.create(order=order, product=product, quantity=quantity, price=product.price)
            application = LoanApplication.objects.create(
                farmer=farmer,
                loan_product=loan_product,
                order=order,
                amount=amount,
                status='PENDING',
                purpose=f"{purpose} - {product.name} x{quantity}",
            )
        
        # Notifications
        farmer_msg = (
            f"Lunyili AgroSmart\n"
            f"Ombi la mkopo wa pembejeo\n"
            f"#{application.id} limepokelewa!\n"
            f"{product.name} x{quantity}\n"
            f"Jumla: TSh {int(amount):,}\n"
            f"Tutakujulisha baada ya siku 2-3."
        )
        self._send_sms(farmer.phone_number, farmer_msg)
        
        supplier_msg = (
            f"Lunyili AgroSmart\n"
            f"Oda mpya #{order.reference}\n"
            f"Mkulima: {farmer.full_name}\n"
            f"Bidhaa: {product.name} x{quantity}\n"
            f"Malipo: Mkopo (Inasubiriwa)"
        )
        self._send_sms(supplier.phone, supplier_msg)
        
        self._end()
        return END, (
            f"✅ OMBI LIMEHIFADHIWA!\n"
            f"====================\n"
            f"{product.name} x{quantity}\n"
            f"Jumla: TSh {int(amount):,}\n"
            f"Ref: #{application.id}\n"
            f"====================\n"
            f"Tutakujulisha baada ya siku 2-3."
        )


    def _create_cash_loan(self, farmer):
        """Create cash loan"""
        product = LoanProduct.objects.get(id=self.data["selected_product_id"])
        amount = Decimal(self.data["loan_amount"])
        purpose = self.data["loan_purpose"]
        
        application = LoanApplication.objects.create(
            farmer=farmer,
            loan_product=product,
            amount=amount,
            status='PENDING',
            purpose=purpose
        )
        
        farmer_msg = (
            f"Lunyili AgroSmart\n"
            f"Ombi la mkopo #{application.id} limepokelewa!\n"
            f"Kiasi: TSh {int(amount):,}\n"
            f"Bidhaa: {product.name}\n"
            f"Tutakujulisha baada ya siku 2-3."
        )
        self._send_sms(farmer.phone_number, farmer_msg)
        
        if product.institution and product.institution.phone:
            inst_msg = (
                f"Lunyili AgroSmart\n"
                f"Ombi jipya la mkopo #{application.id}\n"
                f"Mkulima: {farmer.full_name}\n"
                f"Simu: {farmer.phone_number}\n"
                f"Bidhaa: {product.name}\n"
                f"Kiasi: TSh {int(amount):,}\n"
                f"Sababu: {purpose}"
            )
            self._send_sms(product.institution.phone, inst_msg)
        
        self._end()
        return END, (
            f"✅ OMBI LIMEPOKELEWA!\n"
            f"====================\n"
            f"Bidhaa: {product.name}\n"
            f"Kiasi: TSh {int(amount):,}\n"
            f"Kumbukumbu: #{application.id}\n"
            f"====================\n"
            f"Tutakujulisha baada ya siku 2-3."
        )


    # ======================================================================
    # CHECK LOAN STATUS, HISTORY, SCORE
    # ======================================================================

    def _check_loan_status(self):
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza."
        
        applications = LoanApplication.objects.filter(farmer=farmer).order_by('-created_at')[:5]
        
        if not applications:
            self._end()
            return END, "Hujawahi kuomba mkopo.\n\nPiga *566# tena na chagua 1 kuomba mkopo."
        
        lines = ["HALI YA MIKOPO YAKO\n", "===================="]
        for app in applications:
            status_emoji = {
                'PENDING': '⏳',
                'APPROVED': '✅',
                'FARMER_ACCEPTED': '✅',
                'DISBURSEMENT_PENDING': '⏳',
                'REJECTED': '❌',
                'DISBURSED': '💰',
                'ACTIVE': '💰',
                'PARTIALLY_REPAID': '💵',
                'OVERDUE': '⚠️',
                'FULLY_REPAID': '✔️',
                'REPAID': '✔️',
                'DEFAULTED': '⚠️'
            }.get(app.status, '📌')
            
            lines.append(
                f"{status_emoji} #{app.id} - {app.loan_product.name}\n"
                f"   TSh {int(app.amount):,} | {app.get_status_display()}\n"
                f"   {app.created_at.strftime('%d/%m/%Y')}"
            )
        
        self._end()
        return END, "\n".join(lines)


    def _check_loan_history(self):
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza."
        
        applications = LoanApplication.objects.filter(farmer=farmer)
        
        if not applications.exists():
            self._end()
            return END, "Hujawahi kuomba mkopo."
        
        total = applications.count()
        approved = applications.filter(status='APPROVED').count()
        disbursed = applications.filter(status='DISBURSED').count()
        repaid = applications.filter(status__in=['FULLY_REPAID', 'REPAID']).count()
        
        lines = [
            "HISTORIA YA MIKOPO\n",
            "====================",
            f"Jumla: {total}",
            f"Imekubaliwa: {approved}",
            f"Imetolewa: {disbursed}",
            f"Imelipwa: {repaid}",
            "====================",
        ]
        
        self._end()
        return END, "\n".join(lines)


    def _check_my_score(self):
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza."
        
        if not farmer.loan_eligibility_updated or (
            timezone.now() - farmer.loan_eligibility_updated
        ).days > 7:
            farmer.calculate_credit_readiness()
        
        eligibility = farmer.get_eligibility_level()
        
        self._end()
        return END, (
            f"ALAMA YAKO\n"
            f"====================\n"
            f"Alama: {farmer.credit_readiness_score}/100\n"
            f"Hali: {eligibility['label']}\n"
            f"====================\n"
            f"{eligibility['recommendation']}\n"
            f"====================\n"
            "Alama hii ni kiashiria cha utayari tu.\n"
            "Taasisi ya fedha hufanya uamuzi wa mwisho.\n\n"
            f"Piga *566# tena."
        )


    def _show_eligible_loans(self):
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza."
        
        farmer.calculate_credit_readiness()
        eligibility = farmer.get_eligibility_level()
        products = LoanProduct.objects.filter(
            is_active=True,
            minimum_credit_score__lte=farmer.credit_readiness_score,
        )[:5]
        
        lines = [
            "MIKOPO UNAYOSTAHILI\n",
            "====================",
            f"Alama yako: {farmer.credit_readiness_score}/100",
            f"Hali: {eligibility['label']}",
            "====================",
        ]
        
        if products:
            lines.append("\nBidhaa unazostahili:")
            for p in products:
                lines.append(
                    f"• {p.name}\n"
                    f"  Kiwango: TSh {int(p.min_amount):,}-{int(p.max_amount):,}"
                )
        else:
            lines.append("\nHakuna bidhaa kwa sasa.")
        
        self._end()
        return END, "\n".join(lines)


    # ======================================================================
    # PROFILE COMPLETION
    # ======================================================================

    def _start_profile_completion(self):
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza."
        
        # Check what's missing
        missing = []
        if not farmer.national_id:
            missing.append("1. Namba ya Kitambulisho")
        if not farmer.date_of_birth:
            missing.append("2. Tarehe ya Kuzaliwa")
        if not farmer.farm_size_acres:
            missing.append("3. Ukubwa wa Shamba")
        if not farmer.primary_crop:
            missing.append("4. Zao Kuu")
        if not farmer.years_farming:
            missing.append("5. Miaka ya Kulima")
        if not farmer.has_bank_account and not farmer.has_saccos_account:
            missing.append("6. Akaunti ya Benki/SACCOS")
        
        if not missing:
            self._end()
            return END, (
                f"✅ TAARIFA ZAKO ZIMEKAMILIKA!\n"
                f"Alama yako: {farmer.credit_readiness_score}/100\n"
                f"Piga *566# kuomba mkopo."
            )
        
        self._goto("financial_collect_data")
        return CON, (
            "KAMILISHA TAARIFA\n"
            "====================\n"
            "Taarifa zinazokosekana:\n" + 
            "\n".join(missing) +
            "\n====================\n"
            "Bonyeza 1 kuendelea\n"
            "0. Rudi"
        )

    def _profile_missing_fields(self, farmer):
        fields = [
            ('gender', 'Jinsia (M/F/O)'),
            ('date_of_birth', 'Tarehe ya kuzaliwa (DD/MM/YYYY)'),
            ('national_id', 'Namba ya NIDA'),
            ('region', 'Mkoa'),
            ('district', 'Wilaya'),
            ('ward', 'Kata'),
            ('village', 'Kijiji'),
            ('farm_size_acres', 'Ukubwa wa shamba kwa ekari'),
            ('farm_ownership', 'Umiliki (OWNED/RENTED/BOTH)'),
            ('primary_crop', 'Zao kuu'),
            ('secondary_crop', 'Zao lingine'),
            ('years_farming', 'Miaka ya kulima'),
            ('irrigation_type', 'Aina ya kilimo (RAIN_FED/IRRIGATION/BOTH)'),
            ('estimated_production', 'Uzalishaji unaokadiriwa kwa kilo'),
        ]
        return [(field, prompt) for field, prompt in fields if not getattr(farmer, field)]

    def _handle_financial_collect_data(self, full_text: str, last_input: str):
        if last_input == '0':
            self._goto('financial_menu')
            return CON, self._render_financial_menu()
        if last_input != '1':
            return CON, "Bonyeza 1 kuendelea au 0 kurudi:"
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        missing = self._profile_missing_fields(farmer)
        if not missing:
            self._end()
            return END, "Taarifa zako zimekamilika. Piga *566# tena."
        field, prompt = missing[0]
        self.data['profile_field'] = field
        self._goto('financial_profile_value')
        return CON, f"Ingiza {prompt}:"

    def _handle_financial_profile_value(self, full_text: str, last_input: str):
        field = self.data.get('profile_field')
        value = last_input.strip()
        if not field or not value:
            return CON, "Taarifa si sahihi. Jaribu tena:"
        try:
            if field == 'date_of_birth':
                value = datetime.strptime(value, '%d/%m/%Y').date()
            elif field == 'national_id':
                normalized_nida = validate_nida_format(value)
                if not normalized_nida:
                    farmer = Farmer.objects.get(phone_number=self.phone_number)
                    farmer.kyc_status = 'PROVIDED'
                    farmer.kyc_result = {'format_valid': False}
                    farmer.save(update_fields=['kyc_status', 'kyc_result', 'updated_at'])
                    raise ValueError
                value = normalized_nida
            elif field in ['farm_size_acres', 'estimated_production']:
                value = Decimal(value)
                if value <= 0:
                    raise ValueError
            elif field == 'years_farming':
                value = int(value)
                if value <= 0:
                    raise ValueError
            elif field == 'gender':
                value = value.upper()
                if value not in ['M', 'F', 'O']:
                    raise ValueError
            elif field == 'farm_ownership' and value.upper() not in ['OWNED', 'RENTED', 'BOTH']:
                raise ValueError
            elif field == 'irrigation_type' and value.upper() not in ['RAIN_FED', 'IRRIGATION', 'BOTH']:
                raise ValueError
            farmer = Farmer.objects.get(phone_number=self.phone_number)
            setattr(farmer, field, value)
            if field == 'national_id':
                farmer.kyc_status = 'FORMAT_VALID'
                farmer.kyc_result = {'note': 'Format checked only; identity not verified'}
                farmer.save(update_fields=[field, 'kyc_status', 'kyc_result', 'updated_at'])
            else:
                farmer.save(update_fields=[field, 'updated_at'])
            farmer.update_profile_completeness()
            farmer.calculate_credit_readiness()
        except (ValueError, TypeError):
            return CON, "Taarifa si sahihi. Tumia muundo ulioombwa:"

        self._goto('financial_collect_data')
        return CON, "Imehifadhiwa. Bonyeza 1 kwa taarifa inayofuata au 0 kurudi:"

    def _show_loan_acceptance(self):
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        application = LoanApplication.objects.filter(
            farmer=farmer, status=LoanStatus.APPROVED
        ).select_related('loan_product').order_by('-approved_date').first()
        if not application:
            self._end()
            return END, "Huna mkopo ulioidhinishwa unaosubiri kukubaliwa."
        product = application.loan_product
        total = application.amount + (application.amount * product.interest_rate / Decimal('100'))
        self.data['acceptance_application_id'] = str(application.id)
        self._goto('financial_acceptance')
        return CON, (
            "MASHARTI YA MKOPO\n"
            f"Kiasi: TSh {int(application.amount):,}\n"
            f"Riba: {product.interest_rate}%\n"
            f"Muda: {product.duration_months} miezi\n"
            f"Jumla ya marejesho: TSh {int(total):,}\n"
            f"Mzunguko: {product.get_repayment_frequency_display()}\n"
            "Malipo ya kwanza: Baada ya utoaji\n"
            "Ada: Kulingana na masharti ya taasisi\n"
            "1. Kubali\n"
            "2. Kataa"
        )

    def _handle_financial_acceptance(self, full_text: str, last_input: str):
        application_id = self.data.get('acceptance_application_id')
        if last_input not in ['1', '2']:
            return CON, "Chagua 1 kukubali au 2 kukataa:"
        application = LoanApplication.objects.filter(
            id=application_id, farmer__phone_number=self.phone_number,
            status=LoanStatus.APPROVED,
        ).first()
        if not application:
            self._end()
            return END, "Mkopo huu haupo au umeshughulikiwa tayari."
        now = timezone.now()
        accepted = last_input == '1'
        application.accepted_at = now
        application.acceptance_status = 'ACCEPTED' if accepted else 'DECLINED'
        application.accepted_terms_version = f"{application.loan_product.id}:{application.loan_product.updated_at.isoformat()}"
        application.acceptance_session_reference = self.session.session_id
        application.status = LoanStatus.FARMER_ACCEPTED if accepted else LoanStatus.FARMER_DECLINED
        application.save(update_fields=['accepted_at', 'acceptance_status', 'accepted_terms_version', 'acceptance_session_reference', 'status', 'updated_at'])
        if not accepted:
            self._end()
            return END, "Umeukataa mkopo. Hakuna fedha zilizotolewa."
        try:
            disbursement = request_disbursement(application)
        except ValueError as exc:
            self.logger.warning("Disbursement blocked for %s: %s", application.id, exc)
            self._end()
            return END, "Mkopo umekubaliwa, lakini utoaji unasubiri taarifa za malipo zilizothibitishwa."
        self._end()
        if disbursement.status != 'SUCCESS':
            return END, "Mkopo umekubaliwa. Utoaji unasubiri uthibitisho wa mtoa huduma wa malipo."
        return END, "Mkopo umekubaliwa na umetolewa. Piga *566# kuona ratiba ya marejesho."

    def _render_financial_acceptance(self):
        return self._show_loan_acceptance()[1]

    def _show_repayment_schedule(self):
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        loan = Loan.objects.filter(
            application__farmer=farmer,
            status__in=[LoanStatus.DISBURSED, LoanStatus.ACTIVE, LoanStatus.PARTIALLY_REPAID, LoanStatus.OVERDUE],
        ).select_related('application__loan_product').order_by('-disbursed_at').first()
        if not loan:
            self._end()
            return END, "Huna mkopo unaoendelea."
        rows = loan.repayments.order_by('installment_number')[:6]
        if not rows:
            self._end()
            return END, "Ratiba bado inaandaliwa. Jaribu tena baadaye."
        lines = [
            'RATIBA YA MAREJESHO',
            f'Baki: TSh {int(loan.outstanding_balance):,}',
        ]
        for row in rows:
            lines.append(f'{row.installment_number}. {row.due_date.strftime("%d/%m/%Y")} TSh {int(row.remaining_balance):,} {row.get_status_display()}')
        self._end()
        return END, '\n'.join(lines)

    def _start_repayment_payment(self):
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        loan = Loan.objects.filter(application__farmer=farmer, status__in=[LoanStatus.DISBURSED, LoanStatus.ACTIVE, LoanStatus.PARTIALLY_REPAID, LoanStatus.OVERDUE]).order_by('-disbursed_at').first()
        if not loan:
            self._end()
            return END, "Huna mkopo unaoendelea."
        row = loan.repayments.filter(status__in=[RepaymentStatus.DUE, RepaymentStatus.OVERDUE, RepaymentStatus.PARTIALLY_PAID]).order_by('installment_number').first()
        if not row:
            self._end()
            return END, "Hakuna malipo yanayodaiwa kwa sasa."
        payment = initiate_payment(loan, row.remaining_balance)
        self._end()
        return END, (
            f'MALIPO YA MAREJESHO\nKiasi: TSh {int(payment.amount):,}\n'
            f'Ref: {payment.provider_reference}\n'
            'Malipo hayajathibitishwa. Tumia njia ya malipo uliyopewa na subiri ujumbe wa uthibitisho.\n'
            'Usitume tena bila kutumia Ref hii.'
        )


    # ======================================================================
    # RENDER METHODS
    # ======================================================================

    def _render_financial_menu(self) -> str:
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        return (
            "HUDUMA ZA KIFEDHA\n"
            "====================\n"
            f"Kamilisho: {farmer.profile_completeness}%\n"
            "====================\n"
            "1. Omba Mkopo\n"
            "2. Angalia Hali ya Mkopo\n"
            "3. Historia ya Mikopo\n"
            "4. Alama Yangu\n"
            "5. Kamilisha Taarifa\n"
            "6. Mikopo Ninayostahili\n"
            "6. Mikopo Ninayostahili\n"
            "7. Kubali Mkopo Ulioidhinishwa\n"
            "8. Ratiba ya Marejesho\n"
            "9. Malipo\n"
            "0. Nyumbani"
        )


    def _render_financial_loan_type(self) -> str:
        return (
            "CHAGUA AINA YA MKOPO\n"
            "====================\n"
            "1. Mkopo wa Pembejeo\n"
            "   (Mbolea, Mbegu, Dawa)\n"
            "2. Mkopo wa Uzalishaji\n"
            "3. Mkopo wa Biashara ya Mazao\n"
            "0. Rudi"
        )


    def _render_financial_input_category(self) -> str:
        categories = self.data.get('input_category_ids', [])
        lines = []
        for i, cat_id in enumerate(categories[:5], 1):
            try:
                cat = Category.objects.get(id=cat_id)
                lines.append(f"{i}. {cat.name}")
            except:
                pass
        lines.append("0. Rudi")
        return _menu("CHAGUA PEMBEJEO\nChagua aina ya pembejeo:", lines)


    def _render_financial_input_product(self) -> str:
        products = self.data.get('input_product_ids', [])
        lines = []
        for i, prod_id in enumerate(products[:9], 1):
            try:
                p = Product.objects.get(id=prod_id)
                lines.append(f"{i}. {p.name}\n   TSh {int(p.price):,}/{p.unit}")
            except:
                pass
        lines.append("0. Rudi")
        return _menu("Chagua bidhaa:", lines)


    def _render_financial_products(self) -> str:
        products = self.data.get("loan_products", [])
        lines = []
        for i, p in enumerate(products[:9], 1):
            lines.append(
                f"{i}. {p['name']}\n"
                f"   Riba: {p['interest']}% | Muda: {p['duration']}m"
            )
        lines.append("0. Rudi")
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if farmer:
            lines.append(f"⭐ Alama yako: {farmer.credit_readiness_score}/100")
        return _menu("BIDHAA ZA MKOPO\nChagua bidhaa:", lines)
    
    
    
