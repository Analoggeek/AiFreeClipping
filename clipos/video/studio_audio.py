"""Validated local audio processing used by export and shared-graph playback."""

import math

AUDIO_EFFECTS = {
    "bass": ("Bass EQ · 100 Hz gain dB", -24.0, 24.0, 3.0),
    "presence": ("Presence EQ · 2.5 kHz gain dB", -24.0, 24.0, 3.0),
    "treble": ("Treble EQ · 8 kHz gain dB", -24.0, 24.0, 2.0),
    "noise": ("FFT noise-floor reduction dB", -70.0, -20.0, -45.0),
    "compressor": ("Compressor ratio · threshold −18 dB", 1.0, 12.0, 4.0),
    "limiter": ("Peak limiter ceiling", 0.1, 1.0, 0.9),
    "echo": ("Echo feedback · 120 ms", 0.0, 0.8, 0.25),
    "highpass": ("Voice rumble high-pass Hz", 20.0, 500.0, 80.0),
}


def validate_audio_effects(effects):
    if not isinstance(effects, list) or len(effects) > 8:
        raise ValueError("At most eight audio processors per audio item")
    for effect in effects:
        if (
            not isinstance(effect, dict)
            or set(effect) != {"kind", "amount"}
            or not isinstance(effect["kind"], str)
            or effect["kind"] not in AUDIO_EFFECTS
        ):
            raise ValueError("Unsupported audio processor")
        _, lo, hi, _ = AUDIO_EFFECTS[effect["kind"]]
        value = effect["amount"]
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not lo <= value <= hi
        ):
            raise ValueError("Audio processor amount out of range")
    return effects


def audio_filters(effects):
    validate_audio_effects(effects)
    filters = []
    for effect in effects:
        kind = effect["kind"]
        amount = effect["amount"]
        if kind in ("bass", "presence", "treble"):
            frequency = {"bass": 100, "presence": 2500, "treble": 8000}[kind]
            filters.append(f"equalizer=f={frequency}:t=q:w=0.707:g={amount:.6f}")
        elif kind == "noise":
            filters.append(f"afftdn=nf={amount:.6f}")
        elif kind == "compressor":
            filters.append(
                f"acompressor=threshold=0.12589254:ratio={amount:.6f}:attack=20:release=250:makeup=1"
            )
        elif kind == "limiter":
            filters.append(f"alimiter=limit={amount:.6f}:level=0:attack=0.1")
        elif kind == "echo" and amount:
            filters.append(
                f"aecho=in_gain=1:out_gain=0.8:delays=120:decays={amount:.6f}"
            )
        elif kind == "highpass":
            filters.append(f"highpass=f={amount:.6f}")
    return ",".join(filters) + ("," if filters else "")
