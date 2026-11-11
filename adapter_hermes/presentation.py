"""Plain-text command views. Model tools retain their structured protocol."""
import shlex
import textwrap


WORDMARK = "\n".join((
    "             '||                     .",
    " ....      .. ||    ....  ... ...  .||.    ...   ... ..  .... ...",
    "'' .||   .'  '||  .|...||  ||'  ||  ||   .|  '|.  ||' ''  '|.  |",
    ".|' ||   |.   ||  ||       ||    |  ||   ||   ||  ||       '|.|",
    "'|..'|'  '|..'||.  '|...'  ||...'   '|.'  '|..|' .||.       '|",
    "                           ||                            .. |",
    "                          ''''                            ''",
))


def welcome():
    return '```\n' + WORDMARK + '\n```\n\nWelcome to Adeptory.'


def text(value, limit=500):
    value = str(value).replace("functions.read_file", "the file reader")
    return textwrap.shorten(" ".join(value.split()), width=limit, placeholder="...")


def command(operation, kit):
    return f"/adeptory {operation} {shlex.quote(kit.id)}"


def next_step(instruction):
    return "\n\nNext: " + instruction


def choices(kit):
    lines = []
    for number, choice in enumerate(kit.pending_choices, 1):
        value = kit.adoption.choices.get(choice)
        if isinstance(value, dict) and value.get("status") == "deferred":
            state = "deferred by you; ask before work that depends on it"
        elif isinstance(value, dict) and value.get('status') == 'unresolved':
            state = 'ask when a task needs this fact'
        elif value is not None and value != "":
            state = "decided by you"
        else:
            state = "needs your decision"
        lines.append(f"{number}. {choice_label(choice)} ({state})")
    return lines


def choice_label(choice):
    key, separator, meaning = choice.partition(":")
    label = key.replace("_", " ").strip()
    label = label[:1].upper() + label[1:]
    return text(label + (": " + meaning.strip() if separator else ""), 180)


def overview(kit, *, active=False):
    adopted = kit.adoption.status == "adopted" and kit.adoption.version == kit.version
    state = "active in this chat" if active and adopted else "selected workflow" if adopted else "for your review"
    return f"{text(kit.goal)}\nSubject: {text(kit.subject)} ({state})"


def review(kit, status):
    if not status.get('ready_for_review'):
        construction = status.get('construction', {})
        tasks = construction.get('plan', {}).get('tasks', [])
        complete = sum(task.get('status') == 'complete' for task in tasks)
        current = status.get('next_executable_task')
        lines = ['Building your specialist for ' + text(kit.subject) + '.',
                 f'{complete} of {len(tasks)} construction tasks complete.']
        if current:
            lines.append('Current work: ' + text(current['description']))
        lines.extend(text(gap, 220) for gap in status.get('gaps', [])[:3])
        lines.append('Your request and completed work are saved.')
        return '\n\n'.join(lines)
    lines = [overview(kit), "", "Workflow"]
    for index, step in enumerate(kit.workflow[:6], 1):
        lines.append(f"{index}. {text(step.instruction)}")
        lines.append(f"   Why: {text(step.reason, 160)}")
    if len(kit.workflow) > 6:
        lines.append(f"Plus {len(kit.workflow) - 6} further steps; ask for a guided walkthrough.")
    if not kit.workflow:
        lines.append("Workflow still needs to be prepared.")
    library = status.get('construction', {}).get('library', {})
    if library.get('documents') or library.get('entries'):
        lines.extend(['', 'Library',
                      f"{library.get('documents', 0)} captured sources and {library.get('entries', 0)} authored entries.",
                      'Index: ' + library.get('navigation', ''),
                      'Entries retain their source scope, conditions and review requirements.'])
    lines.extend(["", "Supporting excerpts"])
    for source in kit.sources:
        lines.append(f"- {text(source.title, 160)} ({source.quality}, captured {text(source.retrieved_at, 40)})\n  {source.url}")
        if source.limitations:
            lines.append("  Limits: " + text("; ".join(source.limitations), 220))
    if not kit.sources:
        lines.append("Source research still needs to be captured.")
    if kit.claims:
        support = {}
        for claim in kit.claims:
            support[claim.support] = support.get(claim.support, 0) + 1
        lines.append("Claim review: " + ", ".join(f"{count} {state}" for state, count in support.items()) + ".")
    lines.extend(["", "Readiness"])
    lines.append("Research checklist: " + ("complete for review." if status["ready_for_review"] else "further preparation needed."))
    for capability in kit.capabilities:
        lines.append(f"- {capability.id}: {capability.readiness}. {text(capability.why, 180)}")
    if status["gaps"]:
        lines.append("Preparation to discuss:")
        lines.extend("- " + text(gap, 220) for gap in status["gaps"][:5])
        if len(status["gaps"]) > 5:
            lines.append(f"Plus {len(status['gaps']) - 5} further preparation items; ask for details.")
    if kit.pending_choices:
        lines.extend(["", "Your choices", *choices(kit)])
        lines.append("I will ask about an unresolved fact when a task depends on it.")
    return "Your specialist is ready.\n\n" + "\n".join(lines) + next_step(
        "Tell me what you want the specialist to help with.")


def activated(kit, verb="Activated"):
    lines = [f"{verb} the specialist for {text(kit.subject)}.", text(kit.goal)]
    if kit.workflow:
        lines.append("Workflow starts with: " + text(kit.workflow[0].instruction, 220))
    if kit.pending_choices:
        deferred = sum(isinstance(value, dict) and value.get("status") == "deferred"
                       for value in kit.adoption.choices.values())
        lines.append(f"Your choices: {len(kit.pending_choices) - deferred} decided, {deferred} deferred by you.")
        if deferred:
            lines.append("Deferred choices stay open. I'll ask before work that depends on them.")
    return "\n".join(lines) + next_step(
        "Describe what you want to do in ordinary language. I'll guide you through the workflow and ask for decisions when needed.")


def why(receipt, kit=None):
    if receipt.get("error"):
        return "Adeptory needs attention: " + text(receipt["error"]) + next_step(
            command("review", kit) if kit else "Use /adeptory to review available kits.")
    lines = ["Last task evidence (historical; describes the previous selection)."]
    if receipt.get("kit_id"):
        lines.append(f"Kit: {receipt['kit_id']}, version {receipt.get('version')}; subject: {text(receipt.get('subject', ''))}.")
    lines.append(text(receipt.get("reason", "Context selection recorded.")))
    for selected in receipt.get("selected", []):
        lines.append(f"- {text(selected['id'])}: {text(selected.get('reason', 'selected'))}")
    for note in receipt.get("notes", []):
        lines.append(f"- Unverified lead {text(note['id'])}: {text(note['text'])} (expires {text(note['expires_at'], 40)})")
    if receipt.get("consequence"):
        lines.append(text(receipt["consequence"]["message"]))
    return "\n".join(lines) + next_step("Describe your next task in ordinary language; I'll select relevant guidance for it.")
