"""The Urdu vocabulary alerts must use.

Carried over from the glossary and advisory-tone rules of the first version's
prompt, and extended to the hazards this system raises.
"""

from ews.screening.rules import Level

# Hazard -> the Urdu terms that name it. The first is the one writers are told
# to use; the others are accepted
HAZARD_TERMS_UR: dict[str, tuple[str, ...]] = {
    "heavy_rain": ("بارش",),
    "heatwave": ("گرمی کی لہر",),
    "strong_wind": ("تیز ہوائیں", "ہوائیں", "آندھی"),
    "heavy_snow": ("برفباری", "برف باری"),
    "poor_air_quality": ("ہوا کا معیار", "فضائی آلودگی", "سموگ"),
}

SEVERITY_TERMS_UR: dict[Level, str] = {
    "moderate": "معتدل",
    "severe": "شدید",
    "extreme": "انتہائی شدید",
}

# Weather terms by their English names, for the writer's prompt
WEATHER_TERMS_UR = {
    "rain": "بارش",
    "thunderstorm": "گرج چمک",
    "snow": "برفباری",
    "winds": "ہوائیں",
    "heatwave": "گرمی کی لہر",
    "temperature": "درجہ حرارت",
    "air quality": "ہوا کا معیار",
    "smog": "سموگ",
    "haze": "دھندلاہٹ",
    "fog": "دھند",
    "cloudy": "ابر آلود",
    "overcast": "مکمل ابر آلود",
    "clear sky": "مطلع صاف",
}

# English weather words written out in Urdu letters -> the term to use instead
TRANSLITERATIONS = {
    "تھنڈر اسٹورم": "گرج چمک",
    "تھنڈرسٹورم": "گرج چمک",
    "رین": "بارش",
    "رین فال": "بارش",
    "اسنو": "برفباری",
    "سنو فال": "برفباری",
    "ونڈ": "ہوائیں",
    "ہیٹ ویو": "گرمی کی لہر",
    "ٹمپریچر": "درجہ حرارت",
    "ایئر کوالٹی": "ہوا کا معیار",
    "ائیر کوالٹی": "ہوا کا معیار",
    "ہیز": "دھندلاہٹ",
    "فوگ": "دھند",
    "کلاؤڈی": "ابر آلود",
    "اوورکاسٹ": "مکمل ابر آلود",
}

# Latin letters allowed in Urdu text: the parts of units and of "PM2.5"
LATIN_UNITS = frozenset({"mm", "cm", "km", "h", "c", "pm", "g", "m"})

# In calendar order, matching ``verifier.MONTHS``
URDU_MONTHS = (
    "جنوری",
    "فروری",
    "مارچ",
    "اپریل",
    "مئی",
    "جون",
    "جولائی",
    "اگست",
    "ستمبر",
    "اکتوبر",
    "نومبر",
    "دسمبر",
)
