#!/usr/bin/env python3
import json

from subprocess import Popen, PIPE
from argparse import ArgumentParser


class SelectableTrack:
    def __init__(self, track):
        self.raw = track
        self.track = track.get("index")
        self.tags = track.get("tags", {})
        self.language = self.tags.get("language")
        self.title = self.tags.get("title")
        self.track_type = track.get("codec_type")
        self.forced = track.get("disposition", {}).get("forced", 1) == 1
        self.dub = track.get("disposition", {}).get("dub", 1) == 1
        self.selected = False

    def __repr__(self):
        metadata = f"{self.language or ''}:{self.title or ''}".strip(":")
        metadata = f"{self.index} {self.track_type} {metadata}"
        if self.forced:
            metadata += " forced"
        if self.selected is None:
            return f"<{__class__} {metadata}>"
        if self.selected:
            return f"[x] {metadata}"
        else:
            return f"[ ] {metadata}"


def get_info(fin):
    params = [
        "ffprobe",
        fin,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
    ]
    process = Popen(params, stdout=PIPE)
    output, err = process.communicate()
    exit_code = process.wait()
    return exit_code == 0, json.loads(output).get("streams")


def write_file(fin, fout, to_remove):
    args = [
        "ffmpeg",
        "-i",
        fin,
        "-c",
        "copy",
        "-map",
        "0",
        "-y",
        "-v",
        "error",
    ]
    for x in to_remove:
        args.append("-map")
        args.append(f"-0:{x}")
    args.append(fout)
    print(
        " ".join(
            ["'%s'" % x.replace("'", "\\'") if " " in x else x for x in args]
        )
    )
    process = Popen(args, stdout=PIPE)
    output, err = process.communicate()
    exit_code = process.wait()
    return exit_code == 0


def get_track_number_by_pattern(pattern, metadata, codec_type=None):
    if not codec_type:
        codec_type = ("subtitle", "audio")
    filtered_metadata = sorted(
        [x for x in metadata if x["codec_type"] in codec_type],
        key=lambda x: int(x.get("tags", {}).get("NUMBER_OF_BYTES", "0")),
    )
    if "subtitle" in codec_type:
        if pattern == "smaller":
            return [filtered_metadata[0]["index"]]
        elif pattern == "bigger":
            return [filtered_metadata[-1]["index"]]
    if pattern.isdigit():
        pattern = int(pattern)
        if pattern < len(filtered_metadata):
            return [filtered_metadata[pattern]["index"]]

    selected = []
    for meta in filtered_metadata:
        for candidate in (
            meta.get("tags", {}).get("language", "").lower(),
            meta.get("tags", {}).get("title", "").lower(),
            "forced" if meta["disposition"].get("forced", 1) else "",
        ):
            if pattern.lower() in candidate:
                selected.append(meta["index"])
    return selected


def main(fin, fout, strip=[], keep=[], info=False, interactive=False):
    _, metadata = get_info(fin)
    if not metadata:
        print("No metadata was queried")
        return
    if interactive:
        tracks = [SelectableTrack(x) for x in metadata]
        print(tracks)
    elif info:
        # print(metadata)
        for track in metadata:
            tags = track.get("tags", {})
            language = tags.get("language")
            title = tags.get("title")
            print(
                f"{track['index']} {track['codec_type']}: "
                f"{title}/{language}",
                end="",
            )
            if track["disposition"]["forced"] == 1:
                print(" forced", end="")
            print()

    if not fout and (strip or keep):
        print("Missing output")
        return

    if strip and keep:
        print("Can only strip or keep, not both")
        return

    if keep:
        digit_tracks = [int(x) for x in keep if x.isdigit()]
        named_tracks = []
        for track in set(keep) - set(digit_tracks):
            track = track.split(":")
            if len(track) < 2:
                print(f"Unrecognized pattern for {track[0]}")
                continue
            if track[0] == "a":
                named_tracks.extend(
                    get_track_number_by_pattern(track[1], metadata, ("audio",))
                )
            elif track[0] == "s":
                named_tracks.extend(
                    get_track_number_by_pattern(
                        track[1], metadata, ("subtitle",)
                    )
                )
        track_to_strip = set(
            [
                m["index"]
                for m in metadata
                if m["codec_type"] in ("audio", "subtitle")
            ]
        ) - set(named_tracks)
        for d in digit_tracks:
            if d in track_to_strip:
                track_to_strip.remove(d)
        write_file(fin, fout, track_to_strip)
    elif strip:
        digit_tracks = [int(x) for x in strip if x.isdigit()]
        named_tracks = []
        for track in set(strip) - set(digit_tracks):
            track = track.split(":")
            if len(track) < 2:
                print(f"Unrecognized pattern for {track[0]}")
                continue
            if track[0] == "a":
                named_tracks.extend(
                    get_track_number_by_pattern(track[1], metadata, ("audio",))
                )
            elif track[0] == "s":
                named_tracks.extend(
                    get_track_number_by_pattern(
                        track[1], metadata, ("subtitle",)
                    )
                )
        track_to_strip = set()
        track_to_strip.update(digit_tracks)
        track_to_strip.update(filter(lambda x: x, named_tracks))
        write_file(fin, fout, digit_tracks + named_tracks)


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Strip or keep the selected tracks from files"
    )
    parser.add_argument("input", action="store")
    parser.add_argument("--output", "-o", action="store")
    parser.add_argument(
        "--strip", "-s", action="store", nargs="+", required=False
    )
    parser.add_argument(
        "--keep", "-k", action="store", nargs="+", required=False
    )
    parser.add_argument("--info", action="store_true")

    args = parser.parse_args()
    main(
        args.input,
        args.output,
        strip=args.strip,
        keep=args.keep,
        info=args.info,
    )
