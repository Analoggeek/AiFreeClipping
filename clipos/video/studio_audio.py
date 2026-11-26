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


DUCK_DEFAULTS = {
    "threshold_db": -24.0,
    "ratio": 6.0,
    "attack_ms": 20.0,
    "release_ms": 350.0,
}


def validate_ducking(role, settings):
    if role not in ("dialogue", "music", "neutral"):
        raise ValueError("Choose dialogue, music or neutral audio role")
    if not isinstance(settings, dict):
        raise ValueError("Ducking settings must be an object")
    if not settings:
        return settings
    if role != "music" or set(settings) != set(DUCK_DEFAULTS):
        raise ValueError("Ducking requires a music item and complete settings")
    limits = {
        "threshold_db": (-60.0, 0.0),
        "ratio": (1.0, 20.0),
        "attack_ms": (1.0, 2000.0),
        "release_ms": (10.0, 5000.0),
    }
    for key, (lo, hi) in limits.items():
        value = settings[key]
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not lo <= value <= hi
        ):
            raise ValueError("Invalid ducking parameter: " + key)
    return settings


def ducking_graph(entries, duration, dialogue_available=False):
    """Return additional filters and labels; measured dialogue drives music.

    Entries are (label, role, ducking-settings). Voice remains audible once;
    split copies feed only the sidechain. Neutral/game tracks never drive it.
    """
    for _, role, settings in entries:
        validate_ducking(role, settings)
    targets = [
        i
        for i, (_, role, settings) in enumerate(entries)
        if role == "music" and settings
    ]
    labels = [label for label, _, _ in entries]
    if not targets:
        return [], labels
    voices = [i for i, (_, role, _) in enumerate(entries) if role == "dialogue"]
    if not voices:
        if dialogue_available:
            return [], labels
        raise ValueError("Automatic music ducking requires an enabled dialogue track")
    parts = [f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.8f}[duck_silence]"]
    control = ["[duck_silence]"]
    for index in voices:
        parts.append(
            f"{labels[index]}asplit=2[duck_main_{index}][duck_control_{index}]"
        )
        labels[index] = f"[duck_main_{index}]"
        control.append(f"[duck_control_{index}]")
    parts.append(
        "".join(control)
        + f"amix=inputs={len(control)}:duration=first:dropout_transition=0,volume={len(control)}[duck_bus]"
    )
    if len(targets) > 1:
        parts.append(
            "[duck_bus]asplit="
            + str(len(targets))
            + "".join(f"[duck_bus_{i}]" for i in range(len(targets)))
        )
    for slot, index in enumerate(targets):
        settings = entries[index][2]
        bus = "[duck_bus]" if len(targets) == 1 else f"[duck_bus_{slot}]"
        threshold = 10 ** (settings["threshold_db"] / 20)
        parts.append(
            f"{labels[index]}{bus}sidechaincompress=threshold={threshold:.10f}:ratio={settings['ratio']:.8f}:attack={settings['attack_ms']:.8f}:release={settings['release_ms']:.8f}:makeup=1[duck_music_{index}]"
        )
        labels[index] = f"[duck_music_{index}]"
    return parts, labels
