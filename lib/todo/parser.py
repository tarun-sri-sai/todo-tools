import logging
import re
from hashlib import sha1
from .exceptions import TodoParserError

logging.getLogger()


def _normalize_newlines(text):
    return re.sub(r"\r\n", "\n", text.strip())


def _split_blocks(text):
    text_blocks = re.split(r"\n[\n\s]*\n", text)
    return [block.split("\n") for block in text_blocks]


def _is_category_block(block):
    if len(block) != 3 or len(block[0]) != 32 or block[0][0] != "*":
        return False

    start = set(block[0])
    end = set(block[-1])

    return (
        all(l == l.lstrip() and l for l in block) and
        len(start) == len(end) == 1 and
        start == end and
        len(block[0]) == len(block[-1])
    )


def _is_finished(block):
    return len(block) >= 2 and bool(re.match(r"^\[DONE\].*$", block[-1]))


def _parse_blocks(blocks):
    block_data = []
    for block in blocks:
        if _is_category_block(block):
            block_data.append({
                "category": block[1],
                "id": sha1(block[1].encode()).hexdigest()
            })
            continue

        curr_indent = None
        block_lines = []

        for line in block:
            indent_matches = re.match(r"^((?: {4})*)\S.*$", line)
            if not indent_matches:
                raise TodoParserError(f"invalid indentation for \"{line}\"")

            indent = indent_matches.group(1)
            if (
                curr_indent is not None and
                indent != curr_indent
            ):
                raise TodoParserError(
                    f"inconsistent indentation for \"{line}\""
                )

            if curr_indent is None:
                curr_indent = indent

            block_lines.append(line.strip())

        block_data.append({
            "level": len(curr_indent) // 4,
            "title": block_lines[0],
            "updates": block_lines[1:],
            "id": sha1(block_lines[0].encode()).hexdigest(),
            "finished": _is_finished(block_lines)
        })

    return block_data


def _validate_parents(block_data):
    curr_indents = [-1]
    curr_category = ""
    first_block = True
    for block in block_data:
        if "category" in block:
            first_block = True
            curr_indents = [-1]
            curr_category = block["category"]
            continue

        if first_block and block["level"] > 0:
            raise TodoParserError(
                f"invalid first task for {curr_category}"
            )

        while curr_indents and curr_indents[-1] >= block["level"]:
            curr_indents.pop()

        if (
            block["level"] - 1 != curr_indents[-1]
        ):
            raise TodoParserError(
                f"invalid parent task for \"{block['title']}\""
            )

        curr_indents.append(block["level"])
        first_block = False


def _validate_block_data(block_data):
    if len(block_data) == 0:
        raise TodoParserError("empty todo")

    if "category" not in block_data[0]:
        logging.debug("first block must be a category")

    _validate_parents(block_data)


def _build_task_map(block_data):
    dummy_task = {"level": -1, "id": ""}

    task_map = {}
    curr_category = None
    curr_parents = [dummy_task]

    for block in block_data:
        if "category" in block:
            curr_category = block["category"]
            curr_parents = [dummy_task]
            continue

        current_task = {
            "title": block["title"],
            "updates": block["updates"],
            "finished": block["finished"],
        }

        if curr_category is not None:
            current_task["category"] = curr_category

        while curr_parents and curr_parents[-1]["level"] >= block["level"]:
            curr_parents.pop()

        task_sha = sha1()
        for parent in curr_parents[1:]:
            task_sha.update(parent["id"].encode())
        task_sha.update(block["id"].encode())

        current_task["id"] = task_sha.hexdigest()
        current_task["parentTasks"] = [
            parent["title"] for parent in curr_parents[1:]
        ]
        current_task["finished"] |= (
            any(parent.get("finished", False) for parent in curr_parents)
        )

        task_map[current_task["id"]] = current_task
        curr_parents.append(block)

    return task_map


def parse_todo(text):
    try:
        text = _normalize_newlines(text)
        blocks = _split_blocks(text)

        block_data = _parse_blocks(blocks)
        _validate_block_data(block_data)

        return _build_task_map(block_data)
    except TodoParserError:
        raise
    except Exception as e:
        raise TodoParserError("failed to parse todo") from e
