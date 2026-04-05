"""Translation strings for RetailOS.

Each language is a dict of translation keys to translated strings.
Keys follow a dot-notation pattern: module.context.key
"""

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # ── General ──
        "app.name": "RetailOS",
        "app.tagline": "Smart Store Management",
        "common.yes": "Yes",
        "common.no": "No",
        "common.ok": "OK",
        "common.cancel": "Cancel",
        "common.save": "Save",
        "common.delete": "Delete",
        "common.edit": "Edit",
        "common.search": "Search",
        "common.filter": "Filter",
        "common.loading": "Loading...",
        "common.error": "Something went wrong",
        "common.success": "Success",
        "common.total": "Total",
        "common.date": "Date",
        "common.time": "Time",
        "common.amount": "Amount",
        "common.quantity": "Quantity",
        "common.status": "Status",
        "common.actions": "Actions",
        "common.no_data": "No data available",

        # ── Auth ──
        "auth.login": "Login",
        "auth.logout": "Logout",
        "auth.username": "Username",
        "auth.password": "Password",
        "auth.login_success": "Logged in successfully",
        "auth.login_failed": "Invalid username or password",
        "auth.session_expired": "Session expired. Please login again",

        # ── Inventory ──
        "inventory.title": "Inventory",
        "inventory.stock": "Stock",
        "inventory.low_stock": "Low Stock",
        "inventory.out_of_stock": "Out of Stock",
        "inventory.reorder": "Reorder",
        "inventory.expiry_alert": "Expiry Alert",
        "inventory.stock_updated": "Stock updated successfully",
        "inventory.product_name": "Product Name",
        "inventory.sku": "SKU",
        "inventory.price": "Price",
        "inventory.cost_price": "Cost Price",
        "inventory.category": "Category",

        # ── Orders ──
        "orders.title": "Orders",
        "orders.new_order": "New Order",
        "orders.order_id": "Order ID",
        "orders.customer": "Customer",
        "orders.items": "Items",
        "orders.total": "Total",
        "orders.status.pending": "Pending",
        "orders.status.confirmed": "Confirmed",
        "orders.status.delivered": "Delivered",
        "orders.status.cancelled": "Cancelled",

        # ── Udhaar / Credit ──
        "udhaar.title": "Udhaar (Credit)",
        "udhaar.balance": "Outstanding Balance",
        "udhaar.credit_limit": "Credit Limit",
        "udhaar.payment_received": "Payment Received",
        "udhaar.reminder_sent": "Reminder Sent",
        "udhaar.overdue": "Overdue",

        # ── Customers ──
        "customers.title": "Customers",
        "customers.name": "Name",
        "customers.phone": "Phone",
        "customers.loyalty_points": "Loyalty Points",

        # ── Reports ──
        "reports.title": "Reports",
        "reports.sales": "Sales Report",
        "reports.pnl": "Profit & Loss",
        "reports.gst": "GST Report",
        "reports.inventory": "Inventory Report",
        "reports.download": "Download",

        # ── Staff ──
        "staff.title": "Staff",
        "staff.clock_in": "Clock In",
        "staff.clock_out": "Clock Out",
        "staff.attendance": "Attendance",
        "staff.performance": "Performance",

        # ── Notifications ──
        "notifications.title": "Notifications",
        "notifications.mark_read": "Mark as Read",
        "notifications.no_notifications": "No notifications",

        # ── Voice ──
        "voice.listening": "Listening...",
        "voice.processing": "Processing your command...",
        "voice.not_understood": "Sorry, I didn't understand that. Please try again.",
        "voice.command_executed": "Command executed",
    },

    "hi": {
        # ── General ──
        "app.name": "RetailOS",
        "app.tagline": "स्मार्ट दुकान प्रबंधन",
        "common.yes": "हाँ",
        "common.no": "नहीं",
        "common.ok": "ठीक है",
        "common.cancel": "रद्द करें",
        "common.save": "सहेजें",
        "common.delete": "हटाएँ",
        "common.edit": "संपादित करें",
        "common.search": "खोजें",
        "common.filter": "फ़िल्टर",
        "common.loading": "लोड हो रहा है...",
        "common.error": "कुछ गड़बड़ हो गई",
        "common.success": "सफल",
        "common.total": "कुल",
        "common.date": "तारीख",
        "common.time": "समय",
        "common.amount": "राशि",
        "common.quantity": "मात्रा",
        "common.status": "स्थिति",
        "common.actions": "कार्रवाई",
        "common.no_data": "कोई डेटा उपलब्ध नहीं",

        # ── Auth ──
        "auth.login": "लॉगिन",
        "auth.logout": "लॉगआउट",
        "auth.username": "उपयोगकर्ता नाम",
        "auth.password": "पासवर्ड",
        "auth.login_success": "सफलतापूर्वक लॉगिन हुआ",
        "auth.login_failed": "गलत उपयोगकर्ता नाम या पासवर्ड",
        "auth.session_expired": "सत्र समाप्त हो गया। कृपया फिर से लॉगिन करें",

        # ── Inventory ──
        "inventory.title": "इन्वेंटरी",
        "inventory.stock": "स्टॉक",
        "inventory.low_stock": "कम स्टॉक",
        "inventory.out_of_stock": "स्टॉक खत्म",
        "inventory.reorder": "पुनः ऑर्डर",
        "inventory.expiry_alert": "एक्सपायरी अलर्ट",
        "inventory.stock_updated": "स्टॉक सफलतापूर्वक अपडेट हुआ",
        "inventory.product_name": "उत्पाद का नाम",
        "inventory.sku": "SKU",
        "inventory.price": "कीमत",
        "inventory.cost_price": "लागत मूल्य",
        "inventory.category": "श्रेणी",

        # ── Orders ──
        "orders.title": "ऑर्डर",
        "orders.new_order": "नया ऑर्डर",
        "orders.order_id": "ऑर्डर ID",
        "orders.customer": "ग्राहक",
        "orders.items": "आइटम",
        "orders.total": "कुल",
        "orders.status.pending": "लंबित",
        "orders.status.confirmed": "पुष्टि हुई",
        "orders.status.delivered": "डिलीवर हुआ",
        "orders.status.cancelled": "रद्द",

        # ── Udhaar / Credit ──
        "udhaar.title": "उधार",
        "udhaar.balance": "बकाया राशि",
        "udhaar.credit_limit": "उधार सीमा",
        "udhaar.payment_received": "भुगतान प्राप्त",
        "udhaar.reminder_sent": "रिमाइंडर भेजा गया",
        "udhaar.overdue": "बकाया अवधि पार",

        # ── Customers ──
        "customers.title": "ग्राहक",
        "customers.name": "नाम",
        "customers.phone": "फ़ोन",
        "customers.loyalty_points": "लॉयल्टी पॉइंट्स",

        # ── Reports ──
        "reports.title": "रिपोर्ट",
        "reports.sales": "बिक्री रिपोर्ट",
        "reports.pnl": "लाभ और हानि",
        "reports.gst": "GST रिपोर्ट",
        "reports.inventory": "इन्वेंटरी रिपोर्ट",
        "reports.download": "डाउनलोड",

        # ── Staff ──
        "staff.title": "कर्मचारी",
        "staff.clock_in": "हाज़िरी लगाएँ",
        "staff.clock_out": "छुट्टी करें",
        "staff.attendance": "उपस्थिति",
        "staff.performance": "प्रदर्शन",

        # ── Notifications ──
        "notifications.title": "सूचनाएँ",
        "notifications.mark_read": "पढ़ा हुआ करें",
        "notifications.no_notifications": "कोई सूचना नहीं",

        # ── Voice ──
        "voice.listening": "सुन रहा है...",
        "voice.processing": "आपकी बात समझ रहा है...",
        "voice.not_understood": "माफ़ कीजिए, समझ नहीं आया। कृपया फिर से बोलें।",
        "voice.command_executed": "कमांड पूरी हुई",
    },

    "mr": {
        # ── General ──
        "app.name": "RetailOS",
        "app.tagline": "स्मार्ट दुकान व्यवस्थापन",
        "common.yes": "हो",
        "common.no": "नाही",
        "common.ok": "ठीक आहे",
        "common.cancel": "रद्द करा",
        "common.save": "जतन करा",
        "common.delete": "हटवा",
        "common.edit": "संपादित करा",
        "common.search": "शोधा",
        "common.filter": "फिल्टर",
        "common.loading": "लोड होत आहे...",
        "common.error": "काहीतरी चूक झाली",
        "common.success": "यशस्वी",
        "common.total": "एकूण",
        "common.amount": "रक्कम",
        "common.quantity": "प्रमाण",

        # ── Inventory ──
        "inventory.title": "इन्व्हेंटरी",
        "inventory.stock": "स्टॉक",
        "inventory.low_stock": "कमी स्टॉक",
        "inventory.out_of_stock": "स्टॉक संपला",
        "inventory.reorder": "पुन्हा ऑर्डर",

        # ── Orders ──
        "orders.title": "ऑर्डर",
        "orders.new_order": "नवीन ऑर्डर",
        "orders.customer": "ग्राहक",

        # ── Udhaar ──
        "udhaar.title": "उधार",
        "udhaar.balance": "बाकी रक्कम",
        "udhaar.payment_received": "पेमेंट आले",

        # ── Staff ──
        "staff.title": "कर्मचारी",
        "staff.clock_in": "हजेरी लावा",
        "staff.clock_out": "सुट्टी करा",
    },

    "ta": {
        "app.name": "RetailOS",
        "app.tagline": "ஸ்மார்ட் கடை மேலாண்மை",
        "common.yes": "ஆம்",
        "common.no": "இல்லை",
        "common.ok": "சரி",
        "common.cancel": "ரத்து செய்",
        "common.save": "சேமி",
        "common.total": "மொத்தம்",
        "common.amount": "தொகை",
        "inventory.title": "சரக்கு",
        "inventory.stock": "இருப்பு",
        "inventory.low_stock": "குறைந்த இருப்பு",
        "orders.title": "ஆர்டர்கள்",
        "udhaar.title": "கடன்",
        "customers.title": "வாடிக்கையாளர்கள்",
        "staff.title": "ஊழியர்கள்",
    },

    "te": {
        "app.name": "RetailOS",
        "app.tagline": "స్మార్ట్ దుకాణ నిర్వహణ",
        "common.yes": "అవును",
        "common.no": "కాదు",
        "common.ok": "సరే",
        "common.total": "మొత్తం",
        "inventory.title": "ఇన్వెంటరీ",
        "inventory.stock": "స్టాక్",
        "orders.title": "ఆర్డర్లు",
        "udhaar.title": "అప్పు",
        "customers.title": "కస్టమర్లు",
        "staff.title": "సిబ్బంది",
    },

    "bn": {
        "app.name": "RetailOS",
        "app.tagline": "স্মার্ট দোকান ব্যবস্থাপনা",
        "common.yes": "হ্যাঁ",
        "common.no": "না",
        "common.ok": "ঠিক আছে",
        "common.total": "মোট",
        "inventory.title": "ইনভেন্টরি",
        "inventory.stock": "স্টক",
        "orders.title": "অর্ডার",
        "udhaar.title": "বাকি",
        "customers.title": "গ্রাহক",
        "staff.title": "কর্মচারী",
    },

    "gu": {
        "app.name": "RetailOS",
        "app.tagline": "સ્માર્ટ દુકાન વ્યવસ્થાપન",
        "common.yes": "હા",
        "common.no": "ના",
        "common.ok": "બરાબર",
        "common.total": "કુલ",
        "inventory.title": "ઇન્વેન્ટરી",
        "inventory.stock": "સ્ટોક",
        "orders.title": "ઓર્ડર",
        "udhaar.title": "ઉધાર",
        "customers.title": "ગ્રાહકો",
        "staff.title": "કર્મચારી",
    },

    "kn": {
        "app.name": "RetailOS",
        "app.tagline": "ಸ್ಮಾರ್ಟ್ ಅಂಗಡಿ ನಿರ್ವಹಣೆ",
        "common.yes": "ಹೌದು",
        "common.no": "ಇಲ್ಲ",
        "common.ok": "ಸರಿ",
        "common.total": "ಒಟ್ಟು",
        "inventory.title": "ಇನ್ವೆಂಟರಿ",
        "inventory.stock": "ಸ್ಟಾಕ್",
        "orders.title": "ಆರ್ಡರ್‌ಗಳು",
        "udhaar.title": "ಸಾಲ",
        "customers.title": "ಗ್ರಾಹಕರು",
        "staff.title": "ಸಿಬ್ಬಂದಿ",
    },
}

SUPPORTED_LANGUAGES = list(TRANSLATIONS.keys())
DEFAULT_LANGUAGE = "en"
