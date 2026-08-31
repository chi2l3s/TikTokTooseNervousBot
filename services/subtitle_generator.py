from pathlib import Path
import pysubs2

class SubtitleGenerator:
    @staticmethod
    def _wrap_line(words_list: list[str], max_chars: int = 18) -> str:
        lines = []
        cur_line = []
        cur_len = 0

        for w in words_list:
            if cur_len + len(w) + (1 if cur_line else 0) > max_chars and cur_line:
                lines.append(" ".join(cur_line))
                cur_line = [w]
                cur_len = len(w)
            else:
                cur_line.append(w)
                cur_len += len(w) + (1 if cur_len > 0 else 0)

        if cur_line:
            lines.append(" ".join(cur_line))

        return r"\N".join(lines)

    @classmethod
    def generate(
        cls,
        words: list[dict],
        clip_start: float,
        clip_end: float,
        output_path: Path,
        aspect_ratio: str = "9:16",
    ) -> bool:
        valid_words = [
            w for w in words
            if w["start"] >= clip_start - 0.5 and w["end"] <= clip_end + 0.5 and len(w["word"].strip()) > 0
        ]

        if not valid_words:
            return False

        if aspect_ratio == "9:16":
            res_x, res_y = 1080, 1920
            font_size = 24
            margin_v = 240
            outline_val = 3.5
            max_chars = 18
        elif aspect_ratio == "4:3":
            res_x, res_y = 1440, 1080
            font_size = 22
            margin_v = 110
            outline_val = 3.0
            max_chars = 26
        else:
            res_x, res_y = 1920, 1080
            font_size = 20
            margin_v = 90
            outline_val = 2.8
            max_chars = 34

        subs = pysubs2.SSAFile()
        subs.play_res_x = res_x
        subs.play_res_y = res_y

        style = pysubs2.SSAStyle()
        style.fontname = "Montserrat ExtraBold"
        style.fontsize = font_size
        style.primarycolor = pysubs2.Color(255, 255, 255, 0)
        style.secondarycolor = pysubs2.Color(0, 255, 255, 0)
        style.outlinecolor = pysubs2.Color(0, 0, 0, 0)
        style.backcolor = pysubs2.Color(0, 0, 0, 160)
        style.bold = True
        style.outline = outline_val
        style.shadow = 1.5
        style.alignment = pysubs2.Alignment.BOTTOM_CENTER
        style.marginv = margin_v
        style.marginl = 60
        style.marginr = 60
        subs.styles["Default"] = style

        chunks = []
        chunk_size = 3
        for i in range(0, len(valid_words), chunk_size):
            chunks.append(valid_words[i:i + chunk_size])

        for c_idx, chunk in enumerate(chunks):
            phrase_start_ms = int(max(0, (chunk[0]["start"] - clip_start) * 1000))
            if c_idx < len(chunks) - 1:
                next_start_ms = int(max(0, (chunks[c_idx + 1][0]["start"] - clip_start) * 1000))
                phrase_end_ms = min(next_start_ms, int((chunk[-1]["end"] - clip_start + 0.25) * 1000))
            else:
                phrase_end_ms = int((chunk[-1]["end"] - clip_start + 0.3) * 1000)

            if phrase_end_ms <= phrase_start_ms:
                phrase_end_ms = phrase_start_ms + 400

            for active_idx, active_word in enumerate(chunk):
                w_start_ms = int(max(0, (active_word["start"] - clip_start) * 1000))
                ev_start = phrase_start_ms if active_idx == 0 else w_start_ms

                if active_idx < len(chunk) - 1:
                    ev_end = int(max(ev_start + 120, (chunk[active_idx + 1]["start"] - clip_start) * 1000))
                else:
                    ev_end = phrase_end_ms

                if ev_end <= ev_start:
                    ev_end = ev_start + 200

                formatted_tokens = []
                for idx, w in enumerate(chunk):
                    w_text = w["word"].upper()
                    if idx == active_idx:
                        formatted_tokens.append(r"{\c&H00FFFF&\3c&H000000&\bord5}" + w_text + r"{\r}")
                    else:
                        formatted_tokens.append(r"{\c&HFFFFFF&\3c&H000000&\bord3.5}" + w_text)

                line_content = cls._wrap_line(formatted_tokens, max_chars=max_chars)
                event = pysubs2.SSAEvent(start=ev_start, end=ev_end, text=line_content)
                subs.events.append(event)

        subs.save(str(output_path), encoding="utf-8")
        return True