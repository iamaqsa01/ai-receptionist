"""Phase 16 — Pakistan / South-Asian live-voice languages.

Urdu and English are the two languages the notification layer also uses
(see app/integrations/notifications/templates.py); the remaining four are
live-voice only. All of these share the Perso-Arabic script, so the
language detector cannot separate them from text alone — a deliberate
switch is recognised from an explicit language mention, and the STT
provider's own language hint drives the rest (see
app/ai/language/detector.py).

Registered via register_pakistan_languages(), called once from
app/ai/language/__init__.py after the base catalog module has finished
importing (so register_language / LanguageProfile already exist).
"""

from app.ai.language.catalog import LanguageProfile, get_language, register_language

_PROFILES = [
    LanguageProfile(
        code="ur",
        name="Urdu",
        native_name="اردو",
        dialect_note="Standard (Modern Standard) Urdu as spoken in Pakistan.",
        script="Perso-Arabic",
        perso_arabic=True,
        stt_locale="ur",
        tts_locale="ur",
        templates={
            "greeting": "السلام علیکم! {clinic_name} پر کال کرنے کا شکریہ۔ میں آپ کی کیا مدد کر سکتا ہوں؟",
            "ask_name": "برائے مہربانی اپنا پورا نام بتا دیں؟",
            "ask_phone": "آپ سے رابطے کے لیے بہترین فون نمبر کون سا ہے؟",
            "ask_service": "آپ کون سی سروس بُک کروانا چاہیں گے؟ ہمارے پاس یہ دستیاب ہیں: {services}۔",
            "ask_datetime": "آپ کے لیے کون سا دن اور وقت مناسب رہے گا؟",
            "confirm_booking": "ہو گیا، {name} — میں نے {when} کو {service} کے لیے آپ کی اپائنٹمنٹ بُک کر دی ہے۔ کوئی اور بات؟",
            "no_appointment_found": "اس فون نمبر پر مجھے کوئی آنے والی اپائنٹمنٹ نہیں ملی۔",
            "confirm_cancellation": "ہو گیا — میں نے وہ اپائنٹمنٹ منسوخ کر دی ہے۔",
            "ask_new_datetime": "آپ اسے کس دن اور وقت پر منتقل کرنا چاہیں گے؟",
            "confirm_reschedule": "ہو گیا — میں نے آپ کی اپائنٹمنٹ {when} پر منتقل کر دی ہے۔",
            "transfer_to_human": "بالکل، میں آپ کو ابھی ہمارے فرنٹ ڈیسک کے عملے سے ملاتا ہوں۔",
            "clinical_refusal": (
                "میں طبی مشورہ، تشخیص یا نسخہ نہیں دے سکتا — اس میں صرف ہمارا طبی عملہ مدد کر سکتا ہے۔ "
                "کیا میں آپ کی کال اُن کو منتقل کر دوں؟"
            ),
            "unsupported_language": (
                "معذرت، میں فی الحال یہ زبان استعمال نہیں کر سکتا۔ میں ان زبانوں میں مدد کر سکتا ہوں: {languages}۔ "
                "برائے مہربانی کوئی ایک منتخب کریں، یا میں آپ کو فرنٹ ڈیسک سے ملا دیتا ہوں۔"
            ),
            "low_confidence_repeat": "معذرت، مجھے ٹھیک سے سمجھ نہیں آیا — کیا آپ دوبارہ کہہ سکتے ہیں؟",
            "low_confidence_offer_transfer": (
                "مجھے سمجھنے میں دشواری ہو رہی ہے — کیا میں آپ کو ہمارے فرنٹ ڈیسک کے عملے سے ملا دوں؟"
            ),
            "invalid_datetime_past": "وہ وقت گزر چکا ہے — کیا آپ مستقبل کا کوئی دن اور وقت بتا سکتے ہیں؟",
            "ask_provider": "آپ کس ڈاکٹر سے ملنا چاہیں گے؟ ہمارے پاس یہ ہیں: {providers}۔ یا بتا دیں اگر کوئی ترجیح نہیں۔",
            "confirm_booking_prompt": "میں نے {when} کو {service} کے لیے آپ کا نام لکھ لیا ہے — کیا میں بُک کر دوں؟",
            "confirmation_unclear": "معذرت، یہ ہاں تھی یا نہیں؟",
            "processing_request": "ایک لمحہ برائے مہربانی۔",
            "booking_conflict": "معذرت، وہ وقت اب دستیاب نہیں۔ کوئی اور دن یا وقت مناسب رہے گا؟",
            "booking_duplicate": "لگتا ہے کہ اُس وقت کے آس پاس آپ کی پہلے سے ایک اپائنٹمنٹ موجود ہے۔",
        },
    ),
    LanguageProfile(
        code="pa",
        name="Punjabi",
        native_name="پنجابی",
        dialect_note="Pakistani Punjabi in the Shahmukhi (Perso-Arabic) script; conversational Lahori register.",
        script="Perso-Arabic",
        perso_arabic=True,
        stt_locale="pa",
        tts_locale="pa",
        templates={
            "greeting": "السلام علیکم! {clinic_name} تے کال کرن دا شکریہ۔ میں تُہاڈی کیہ مدد کر سکنا واں؟",
            "ask_name": "مہربانی کر کے اپنا پورا ناں دَسو؟",
            "ask_phone": "تُہاڈے نال رابطے لئی سبھ توں چنگا فون نمبر کیہڑا اے؟",
            "ask_service": "تُسیں کیہڑی سروس بُک کرانی چاہندے او؟ ساڈے کول ایہ نیں: {services}۔",
            "ask_datetime": "تُہاڈے لئی کیہڑا دن تے ویلہ ٹھیک رہوے گا؟",
            "confirm_booking": "ہو گیا، {name} — میں {when} نوں {service} لئی تُہاڈی اپائنٹمنٹ بُک کر دِتی اے۔ ہور کوئی گل؟",
            "no_appointment_found": "ایس فون نمبر تے مینوں کوئی آؤن والی اپائنٹمنٹ نئیں لبھی۔",
            "confirm_cancellation": "ہو گیا — میں اوہ اپائنٹمنٹ منسوخ کر دِتی اے۔",
            "ask_new_datetime": "تُسیں ایہنوں کیہڑے دن تے ویلے تے بدلنا چاہندے او؟",
            "confirm_reschedule": "ہو گیا — میں تُہاڈی اپائنٹمنٹ {when} تے بدل دِتی اے۔",
            "transfer_to_human": "بالکل، میں تُہانوں ہُنے ساڈے فرنٹ ڈیسک دے عملے نال ملاندا واں۔",
            "clinical_refusal": (
                "میں طبی صلاح، تشخیص یا نسخہ نئیں دے سکدا — ایس وچ صرف ساڈا طبی عملہ مدد کر سکدا اے۔ "
                "کیہ میں تُہاڈی کال اوہناں نوں بھیج دیاں؟"
            ),
            "unsupported_language": (
                "معافی، میں ہالے ایہ زبان نئیں ورت سکدا۔ میں ایہناں زباناں وچ مدد کر سکنا واں: {languages}۔ "
                "مہربانی کر کے کوئی اِک چُنو، یا میں تُہانوں فرنٹ ڈیسک نال ملا دیاں۔"
            ),
            "low_confidence_repeat": "معافی، مینوں ٹھیک سمجھ نئیں آئی — کیہ تُسیں دوبارہ آکھ سکدے او؟",
            "low_confidence_offer_transfer": (
                "مینوں سمجھن وچ اوکھ ہو رئی اے — کیہ میں تُہانوں ساڈے فرنٹ ڈیسک دے عملے نال ملا دیاں؟"
            ),
            "invalid_datetime_past": "اوہ ویلہ لنگھ چکیا اے — کیہ تُسیں اگے دا کوئی دن تے ویلہ دَس سکدے او؟",
            "ask_provider": "تُسیں کیہڑے ڈاکٹر نوں ملنا چاہندے او؟ ساڈے کول ایہ نیں: {providers}۔ یا دَسو جے کوئی ترجیح نئیں۔",
            "confirm_booking_prompt": "میں {when} نوں {service} لئی تُہاڈا ناں لکھ لیا اے — کیہ میں بُک کر دیاں؟",
            "confirmation_unclear": "معافی، ایہ ہاں سی یا نہیں؟",
            "processing_request": "اِک پل، مہربانی کر کے۔",
            "booking_conflict": "معافی، اوہ ویلہ ہُن دستیاب نئیں۔ کوئی ہور دن یا ویلہ ٹھیک رہوے گا؟",
            "booking_duplicate": "لگدا اے اوس ویلے دے نیڑے تُہاڈی پہلوں اِک اپائنٹمنٹ اے۔",
        },
    ),
    LanguageProfile(
        code="skr",
        name="Saraiki",
        native_name="سرائیکی",
        dialect_note="Saraiki as spoken in southern Punjab, Perso-Arabic script.",
        script="Perso-Arabic",
        perso_arabic=True,
        stt_locale="skr",
        tts_locale="skr",
        templates={
            "greeting": "السلام علیکم! {clinic_name} تے کال کرݨ دا شکریہ۔ میں تُہاڈی کیا مدد کر سگدا ہاں؟",
            "ask_name": "مہربانی کر کے اپݨا پورا ناں ڄاؤ؟",
            "ask_phone": "تُہاڈے نال رابطے کیتے سب توں چنگا فون نمبر کیڑھا اے؟",
            "ask_service": "تُساں کیڑھی سروس بُک کرواوݨ چاہندے او؟ ساݙے کول ایہ ہن: {services}۔",
            "ask_datetime": "تُہاڈے کیتے کیڑھا ڈینھ تے ویلہ ٹھیک رہسی؟",
            "confirm_booking": "تھی ڳیا، {name} — میں {when} تے {service} کیتے تُہاڈی اپائنٹمنٹ بُک کر ڈتی اے۔ ہور کوئی ڳالھ؟",
            "no_appointment_found": "ایں فون نمبر تے میکوں کائی آوݨ آلی اپائنٹمنٹ کائنی لَدھی۔",
            "confirm_cancellation": "تھی ڳیا — میں اوہ اپائنٹمنٹ منسوخ کر ڈتی اے۔",
            "ask_new_datetime": "تُساں ایہ کیڑھے ڈینھ تے ویلے تے بدلاوݨ چاہندے او؟",
            "confirm_reschedule": "تھی ڳیا — میں تُہاڈی اپائنٹمنٹ {when} تے بدل ڈتی اے۔",
            "transfer_to_human": "بالکل، میں تُہاکوں ہݨ ساݙے فرنٹ ڈیسک دے عملے نال ملاندا ہاں۔",
            "clinical_refusal": (
                "میں طبی صلاح، تشخیص یا نسخہ کائنی ڈے سگدا — ایں وچ رڳا ساݙا طبی عملہ مدد کر سگدا اے۔ "
                "کیا میں تُہاڈی کال اوہناں کوں بھیج ڈیاں؟"
            ),
            "unsupported_language": (
                "معافی، میں ہالے ایہ زبان کائنی ورت سگدا۔ میں ایہناں زباناں وچ مدد کر سگدا ہاں: {languages}۔ "
                "مہربانی کر کے کوئی اِک چُنو، یا میں تُہاکوں فرنٹ ڈیسک نال ملا ڈیاں۔"
            ),
            "low_confidence_repeat": "معافی، میکوں ٹھیک سمجھ کائنی آئی — کیا تُساں ڳیں واری ڄو سگدے او؟",
            "low_confidence_offer_transfer": (
                "میکوں سمجھݨ وچ اوکھ تھی رہی اے — کیا میں تُہاکوں ساݙے فرنٹ ڈیسک دے عملے نال ملا ڈیاں؟"
            ),
            "invalid_datetime_past": "اوہ ویلہ لنگھ ڳیا اے — کیا تُساں اڳوں دا کوئی ڈینھ تے ویلہ ڄو سگدے او؟",
            "ask_provider": "تُساں کیڑھے ڈاکٹر کوں ملݨ چاہندے او؟ ساݙے کول ایہ ہن: {providers}۔ یا ڄاؤ جے کائی ترجیح کائنی۔",
            "confirm_booking_prompt": "میں {when} تے {service} کیتے تُہاڈا ناں لکھ گھدا اے — کیا میں بُک کر ڈیاں؟",
            "confirmation_unclear": "معافی، ایہ ہاں ہئی یا نہ؟",
            "processing_request": "اِک پل، مہربانی کر کے۔",
            "booking_conflict": "معافی، اوہ ویلہ ہݨ دستیاب کائنی۔ کوئی ہور ڈینھ یا ویلہ ٹھیک رہسی؟",
            "booking_duplicate": "لڳدا اے اوں ویلے دے نیڑے تُہاڈی پہلوں اِک اپائنٹمنٹ اے۔",
        },
    ),
    LanguageProfile(
        code="sd",
        name="Sindhi",
        native_name="سنڌي",
        dialect_note="Standard Sindhi as spoken in Sindh, Perso-Arabic (Sindhi) script.",
        script="Perso-Arabic",
        perso_arabic=True,
        stt_locale="sd",
        tts_locale="sd",
        templates={
            "greeting": "السلام عليڪم! {clinic_name} تي ڪال ڪرڻ لاءِ مهرباني. مان اوهان جي ڪهڙي مدد ڪري سگهان ٿو؟",
            "ask_name": "مهرباني ڪري پنهنجو پورو نالو ٻڌايو؟",
            "ask_phone": "اوهان سان رابطي لاءِ بهترين فون نمبر ڪهڙو آهي؟",
            "ask_service": "اوهان ڪهڙي سروس بُڪ ڪرائڻ چاهيندؤ؟ اسان وٽ هي آهن: {services}.",
            "ask_datetime": "اوهان لاءِ ڪهڙو ڏينهن ۽ وقت مناسب رهندو؟",
            "confirm_booking": "ٿي ويو، {name} — مون {when} تي {service} لاءِ اوهان جي اپائنٽمينٽ بُڪ ڪري ڇڏي آهي. ٻي ڪا ڳالهه؟",
            "no_appointment_found": "هن فون نمبر تي مون کي ڪا ايندڙ اپائنٽمينٽ نه ملي.",
            "confirm_cancellation": "ٿي ويو — مون اها اپائنٽمينٽ منسوخ ڪري ڇڏي آهي.",
            "ask_new_datetime": "اوهان ان کي ڪهڙي ڏينهن ۽ وقت تي منتقل ڪرڻ چاهيندؤ؟",
            "confirm_reschedule": "ٿي ويو — مون اوهان جي اپائنٽمينٽ {when} تي منتقل ڪري ڇڏي آهي.",
            "transfer_to_human": "بلڪل، مان اوهان کي هاڻي اسان جي فرنٽ ڊيسڪ عملي سان ملايان ٿو.",
            "clinical_refusal": (
                "مان طبي صلاح، تشخيص يا نسخو نه ٿو ڏئي سگهان — ان ۾ رڳو اسان جو طبي عملو مدد ڪري سگهي ٿو. "
                "ڇا مان اوهان جي ڪال انهن ڏانهن موڪليان؟"
            ),
            "unsupported_language": (
                "معافي، مان اڃا هيءَ ٻولي استعمال نٿو ڪري سگهان. مان انهن ٻولين ۾ مدد ڪري سگهان ٿو: {languages}. "
                "مهرباني ڪري ڪا هڪ چونڊيو، يا مان اوهان کي فرنٽ ڊيسڪ سان ملايان."
            ),
            "low_confidence_repeat": "معافي، مون کي چڱيءَ طرح سمجهه ۾ نه آيو — ڇا اوهان ٻيهر چئي سگهو ٿا؟",
            "low_confidence_offer_transfer": (
                "مون کي سمجهڻ ۾ ڏکيائي ٿي رهي آهي — ڇا مان اوهان کي اسان جي فرنٽ ڊيسڪ عملي سان ملايان؟"
            ),
            "invalid_datetime_past": "اهو وقت گذري چڪو آهي — ڇا اوهان مستقبل جو ڪو ڏينهن ۽ وقت ٻڌائي سگهو ٿا؟",
            "ask_provider": "اوهان ڪهڙي ڊاڪٽر سان ملڻ چاهيندؤ؟ اسان وٽ هي آهن: {providers}. يا ٻڌايو جيڪڏهن ڪا ترجيح ناهي.",
            "confirm_booking_prompt": "مون {when} تي {service} لاءِ اوهان جو نالو لکي ورتو آهي — ڇا مان بُڪ ڪري ڇڏيان؟",
            "confirmation_unclear": "معافي، اها ها هئي يا نه؟",
            "processing_request": "هڪ لمحو، مهرباني ڪري.",
            "booking_conflict": "معافي، اهو وقت هاڻي موجود ناهي. ٻيو ڪهڙو ڏينهن يا وقت مناسب رهندو؟",
            "booking_duplicate": "ائين ٿو لڳي ته ان وقت جي ويجهو اوهان جي اڳ ۾ ئي هڪ اپائنٽمينٽ آهي.",
        },
    ),
    LanguageProfile(
        code="ps",
        name="Pashto",
        native_name="پښتو",
        dialect_note="Pashto as spoken in Khyber Pakhtunkhwa, Perso-Arabic (Pashto) script.",
        script="Perso-Arabic",
        perso_arabic=True,
        stt_locale="ps",
        tts_locale="ps",
        templates={
            "greeting": "السلام علیکم! {clinic_name} ته د زنګ وهلو مننه. زه ستاسو څنګه مرسته کولی شم؟",
            "ask_name": "مهرباني وکړئ خپل بشپړ نوم راکړئ؟",
            "ask_phone": "ستاسو سره د اړیکې لپاره غوره تلیفون شمېره کومه ده؟",
            "ask_service": "تاسو کومه سروس بک کول غواړئ؟ زموږ سره دا شته: {services}.",
            "ask_datetime": "ستاسو لپاره کومه ورځ او وخت مناسب دی؟",
            "confirm_booking": "ترسره شو، {name} — ما د {when} لپاره ستاسو د {service} ملاقات بک کړ. بل څه؟",
            "no_appointment_found": "پدې تلیفون شمېره باندې ما هېڅ راتلونکی ملاقات و نه موند.",
            "confirm_cancellation": "ترسره شو — ما هغه ملاقات لغوه کړ.",
            "ask_new_datetime": "تاسو غواړئ دا کومې ورځې او وخت ته بدل کړئ؟",
            "confirm_reschedule": "ترسره شو — ما ستاسو ملاقات {when} ته بدل کړ.",
            "transfer_to_human": "خامخا، زه تاسو اوس زموږ د استقبالیې کارکوونکو سره نښلوم.",
            "clinical_refusal": (
                "زه طبي مشوره، تشخیص یا نسخه نشم درکولی — پدې کې یوازې زموږ طبي کارکوونکي مرسته کولی شي. "
                "ایا زه ستاسو زنګ هغوی ته واړوم؟"
            ),
            "unsupported_language": (
                "بښنه غواړم، زه لا دا ژبه نشم کارولی. زه پدې ژبو کې مرسته کولی شم: {languages}. "
                "مهرباني وکړئ یوه یې وټاکئ، یا زه تاسو د استقبالیې سره ونښلوم."
            ),
            "low_confidence_repeat": "بښنه غواړم، ما سم پوه نشوم — ایا بیا یې ویلی شئ؟",
            "low_confidence_offer_transfer": (
                "ما ته د پوهیدو ستونزه ده — ایا زه تاسو زموږ د استقبالیې کارکوونکو سره ونښلوم؟"
            ),
            "invalid_datetime_past": "هغه وخت تېر شوی — ایا تاسو په راتلونکي کې کومه ورځ او وخت راکولی شئ؟",
            "ask_provider": "تاسو کوم ډاکټر سره لیدل غواړئ؟ زموږ سره دا شته: {providers}. یا ووایاست که کومه غوره توب نلرئ.",
            "confirm_booking_prompt": "ما د {when} لپاره ستاسو نوم د {service} لپاره ولیکه — ایا زه یې بک کړم؟",
            "confirmation_unclear": "بښنه، هغه هو وه که نه؟",
            "processing_request": "یو شېبه مهرباني وکړئ.",
            "booking_conflict": "بښنه غواړم، هغه وخت نور شتون نلري. کومه بله ورځ یا وخت مناسب دی؟",
            "booking_duplicate": "داسې ښکاري چې د هغه وخت شاوخوا ستاسو دمخه یو ملاقات شته.",
        },
    ),
]


def register_pakistan_languages() -> None:
    """Idempotent: registers each profile once. Safe to call on every
    import of app.ai.language."""
    for profile in _PROFILES:
        if get_language(profile.code) is None:
            register_language(profile)
