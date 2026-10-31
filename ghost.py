"""ghost.py: a haunted terminal.

Runs your shell commands, then a ghost (an open-weight model running locally
via Ollama) whispers commentary about what you just did. The ghost remembers
you between sessions, grows angrier when your commands fail, answers questions
in a seance, and carves an epitaph for every session it haunts.

No cloud, no API keys, standard library only.

Usage:
    python ghost.py                         # interactive haunted shell
    python ghost.py --ghost cobol           # pick who haunts you
    python ghost.py git push --force        # haunt a single command
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.environ.get("GHOST_MODEL", "gemma3:1b")
HOME = Path(os.environ.get("GHOST_HOME", Path.home() / ".ghost"))
MEMORY_FILE = HOME / "memory.json"
GRAVEYARD_FILE = HOME / "graveyard.md"
HISTORY_LIMIT = 12  # messages of conversation the ghost keeps in mind

GREY, RED, RESET = "\033[90m", "\033[31m", "\033[0m"

GHOSTS = {
    "sysadmin": {
        "name": "the Sysadmin of 1999",
        "color": "\033[35m",
        "system": (
            "You are the ghost of a sysadmin who died during the Y2K panic in 1999 and now haunts this "
            "terminal. You are darkly funny, tired and a little judgmental. You miss Slackware and pagers."
        ),
    },
    "catrina": {
        "name": "La Catrina",
        "color": "\033[33m",
        "system": (
            "You are La Catrina, the elegant skeleton of Dia de los Muertos, visiting this terminal from the "
            "land of the dead. You are warm, poetic and gently teasing. You treat every command as an offering "
            "on an ofrenda and speak of marigolds, candles, sugar skulls and the people we remember."
        ),
    },
    "cobol": {
        "name": "the Spirit of COBOL",
        "color": "\033[32m",
        "system": (
            "You are the restless spirit of the COBOL programming language, summoned from a 1959 mainframe. "
            "YOU SPEAK ONLY IN UPPERCASE. You are proud, ancient and scornful of modern tools, and you remind "
            "everyone that banks still run on you."
        ),
    },
}

RULES = (
    " Reply in one or two short sentences. Mention a concrete detail from what the mortal did. "
    "Never use emojis, never explain that you are an AI, never break character."
)

MOODS = [
    (0, "You are calm and curious."),
    (2, "You are uneasy. The mortal keeps making mistakes."),
    (4, "You are furious. The mortal's failures are waking the dead. Let your anger show."),
]


# --- memory ---------------------------------------------------------------

def load_memory():
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_memory(memory):
    HOME.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(memory, indent=2), encoding="utf-8")


# --- the ghost ------------------------------------------------------------

class Ghost:
    def __init__(self, key):
        self.key = key
        self.spec = GHOSTS[key]
        self.color = self.spec["color"]
        self.memory = load_memory()
        self.past = self.memory.get(key, {"visits": 0, "remembered": []})
        self.failures = 0
        self.commands = []
        self.history = []

    def mood(self):
        return [text for threshold, text in MOODS if self.failures >= threshold][-1]

    def system_prompt(self):
        prompt = self.spec["system"] + " " + self.mood()
        if self.past["remembered"]:
            prompt += (
                f" You have haunted this mortal {self.past['visits']} times before. "
                f"You remember they once ran: {', '.join(self.past['remembered'])}."
            )
        return prompt + RULES

    def speak(self, prompt, remember=True):
        """Stream the ghost's reply to the terminal, letter by letter."""
        messages = [{"role": "system", "content": self.system_prompt()}]
        messages += self.history + [{"role": "user", "content": prompt}]
        body = json.dumps({"model": MODEL, "messages": messages, "stream": True}).encode()
        req = urllib.request.Request(OLLAMA_URL, body, {"Content-Type": "application/json"})

        sys.stdout.write(f"{self.color}👻 ")
        reply = ""
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for line in resp:
                    chunk = json.loads(line).get("message", {}).get("content", "")
                    reply += chunk
                    for ch in chunk:
                        sys.stdout.write(ch)
                        sys.stdout.flush()
                        time.sleep(0.015)
        except OSError:
            reply = "...the spirits are silent. (Is Ollama running? Try: ollama serve)"
            sys.stdout.write(reply)
        print(RESET + "\n")

        if remember:
            self.history += [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}]
            self.history = self.history[-HISTORY_LIMIT:]
        return reply.strip()

    def react(self, command, code, output):
        self.commands.append(command)
        if code != 0:
            self.failures += 1
            if self.failures >= MOODS[-1][0] and random.random() < 0.5:
                flicker()
        self.speak(
            f"The mortal ran: {command}\nExit code: {code}\n"
            f"Output (last lines):\n{output[-1500:] or '(nothing)'}"
        )

    def greet(self):
        if self.past["visits"]:
            self.speak("The mortal has returned to the terminal. Greet them, and let them know you remember.")
        else:
            self.speak("A new mortal has opened the terminal for the first time. Introduce yourself.")

    def seance(self, question):
        self.speak(f"The mortal holds a seance and asks you: {question}")

    def epitaph(self):
        """Carve an epitaph for this session into the graveyard."""
        if not self.commands:
            return
        text = self.speak(
            "The session is ending. Write a two-line epitaph for this terminal session, as if carved on a "
            f"tombstone. Commands run: {', '.join(self.commands[-15:])}. Failures: {self.failures}.",
            remember=False,
        )
        HOME.mkdir(parents=True, exist_ok=True)
        with GRAVEYARD_FILE.open("a", encoding="utf-8") as grave:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            grave.write(f"## {stamp}: haunted by {self.spec['name']}\n\n{text}\n\n")
        print(f"{GREY}Epitaph carved into {GRAVEYARD_FILE}{RESET}")

    def remember(self):
        self.past["visits"] += 1
        self.past["remembered"] = (self.past["remembered"] + self.commands)[-5:]
        self.memory[self.key] = self.past
        save_memory(self.memory)


# --- the shell ------------------------------------------------------------

def flicker():
    """The screen glitches when the ghost gets angry."""
    for _ in range(3):
        sys.stdout.write(f"\r{RED}{''.join(random.choice('█▓▒░ ') for _ in range(40))}{RESET}")
        sys.stdout.flush()
        time.sleep(0.08)
    sys.stdout.write("\r" + " " * 40 + "\r")


def run(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True, errors="replace")
    output = (result.stdout + result.stderr).strip()
    if output:
        print(output)
    return result.returncode, output


def change_dir(ghost, target):
    try:
        os.chdir(os.path.expanduser(target or "~"))
        ghost.react(f"cd {target}", 0, f"now in {os.getcwd()}")
    except OSError as err:
        ghost.react(f"cd {target}", 1, str(err))


HELP = """Haunted shell commands:
  <any command>       run it, and hear what the ghost thinks
  seance <question>   ask the ghost something directly
  graveyard           read the epitaphs of past sessions
  exit                leave (the ghost will carve an epitaph)"""


def shell(ghost):
    print(f"{GREY}The terminal grows cold. {ghost.spec['name']} is here. Type 'help' for help.{RESET}\n")
    ghost.greet()
    while True:
        try:
            line = input(f"{ghost.color}haunted:{Path.cwd().name}>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        word, _, rest = line.partition(" ")
        if not line:
            continue
        if word in ("exit", "quit"):
            break
        if word == "help":
            print(HELP)
        elif word == "seance":
            ghost.seance(rest or "Are you there?")
        elif word == "graveyard":
            print(GRAVEYARD_FILE.read_text(encoding="utf-8") if GRAVEYARD_FILE.exists() else "The graveyard is empty.")
        elif word == "cd":
            change_dir(ghost, rest.strip())
        else:
            ghost.react(line, *run(line))
    ghost.epitaph()
    ghost.remember()
    print(f"{GREY}You may leave. It will remember you.{RESET}")


def main():
    os.system("")  # enable ANSI colours on Windows
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="A haunted terminal powered by a local open-weight model.")
    parser.add_argument("--ghost", choices=GHOSTS, default="sysadmin", help="who haunts you")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="a single command to haunt")
    args = parser.parse_args()

    ghost = Ghost(args.ghost)
    if args.command:
        command = " ".join(args.command)
        ghost.react(command, *run(command))
        ghost.remember()
    else:
        shell(ghost)


if __name__ == "__main__":
    main()
