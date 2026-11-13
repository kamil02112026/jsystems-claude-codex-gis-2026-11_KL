#!/usr/bin/env bash

# Claude Code Status Line Script
# Docs: https://code.claude.com/docs/en/statusline
#
# 2 lines:
#   line 1: git branch | shortened path
#   line 2: model+effort+fast | context bar | cost | 5h/7d usage | cache hit rate + expiry
#
# Design notes (please keep these properties when editing):
#  - ALWAYS exits 0 and always prints something. Claude Code blanks the status
#    line if the script exits non-zero or produces no output, so `set -e` is
#    deliberately NOT used and every value has an explicit default.
#  - Every JSON field is read in ONE jq call, which also supplies the current
#    time (jq's `now`), so no `date` process is needed.
#  - Minimal process spawns: helpers return through $REPLY instead of $(...)
#    command substitution, which forks a subshell each time. A normal render
#    costs one jq and one git process. Forks are cheap on Linux but expensive
#    in Git Bash on Windows.
#  - Portable across Git Bash on Windows, Linux and macOS bash 3.2: no GNU-only
#    flags, and all money/percentage formatting uses integer math so a
#    comma-decimal locale (e.g. pl_PL) cannot corrupt the output.
#  - The cache expiry countdown only moves when the script re-runs; set
#    "refreshInterval": 30 on statusLine in settings.json so it keeps ticking
#    while the session is idle.

set -uo pipefail

# Local change: prefer jq.exe stored next to this script (e.g. the Claude config dir),
# so the status line works without jq on PATH. Parameter expansion only, no subshell.
# A Windows path (D:/x or D:\x) is rewritten to /d/x, because ':' separates PATH entries.
_sl_dir="${BASH_SOURCE[0]//\\//}"
case "$_sl_dir" in */*) _sl_dir="${_sl_dir%/*}" ;; *) _sl_dir="" ;; esac
case "$_sl_dir" in [A-Za-z]:/*) _sl_drive="${_sl_dir%%:*}"; _sl_dir="/${_sl_drive,,}${_sl_dir#?:}" ;; esac
[ -n "$_sl_dir" ] && PATH="$_sl_dir:$PATH"

# Read stdin without spawning `cat`. read returns 1 at EOF, which is expected.
IFS= read -r -d '' input || true

# ---------- Tokyo Night palette (truecolor, matches ~/.config/wezterm/omarchy.lua) ----------
# Real ESC bytes via ANSI-C quoting, so the final output can use printf '%s' and
# a backslash in a path or branch name is never re-interpreted as an escape.
E=$'\033'
FG="${E}[38;2;169;177;214m"      # #a9b1d6 foreground
DIM="${E}[38;2;120;124;153m"     # #787c99 comment/dim (separators, labels)
ACCENT="${E}[38;2;187;154;247m"  # #bb9af7 magenta (model name)
BLUE="${E}[38;2;122;162;247m"    # #7aa2f7 blue (path, context bar fill)
CYAN="${E}[38;2;68;157;171m"     # #449dab teal (git branch)
GOLD="${E}[38;2;224;175;104m"    # #e0af68 yellow (cost)
GREEN="${E}[38;2;158;206;106m"   # #9ece6a green   - good
ORANGE="${E}[38;2;255;158;100m"  # #ff9e64 orange  - warning
RED="${E}[38;2;247;118;142m"     # #f7768e red     - bad
BAR_FILLED="${E}[38;2;122;162;247m" # #7aa2f7 blue  - filled context
BAR_EMPTY="${E}[38;2;50;52;74m"     # #32344a       - empty context
RESET="${E}[0m"

# Themed separator used between segments
SEP="${DIM} | ${RESET}"

# ---------- Defaults (used if jq is missing or the payload is unexpected) ----------
model_id="-"
model_display="-"
context_used=0
cost_mills=0          # cost in thousandths of a dollar, as an integer
current_dir="-"
ctx_size="-"          # "1M" etc. when the context window exceeds the 200k default
effort_level="-"
fast_mode=0
five_h_pct="-"
five_h_left="-"       # seconds until the 5h window resets
week_pct="-"
week_left="-"         # seconds until the 7d window resets
cache_pct="-"
cache_left="-"        # seconds until the cached prefix goes cold; 0 = already cold

# ---------- Parse the whole payload in a single jq call ----------
# Absent values are emitted as "-" rather than "": @tsv plus `read` with a tab
# IFS collapses runs of empty fields, which would silently shift every later
# value into the wrong variable.
parsed=""
jq_missing=0
if ! command -v jq >/dev/null 2>&1; then
    jq_missing=1
fi
if [ "$jq_missing" -eq 0 ]; then
    parsed=$(jq -r '
      def dash(v): if v == null or v == "" then "-" else v end;
      def pct(v):  if v == null then "-" else (v | floor) end;
      (now | floor) as $now
      # Seconds from now until epoch t, never negative.
      | def left(t): if t == null then "-" else ([t - $now, 0] | max | floor) end;
      # Normalize Windows separators HERE, before @tsv: @tsv escapes a literal
      # backslash as \\, which would otherwise turn C:\Users into C://Users and
      # blank out the parent folder. Only real Windows paths (drive letter or
      # UNC) are touched, so a Linux name containing a backslash survives.
      def winnorm(p):
        if p == null or p == "" then "-"
        elif (p | test("^[A-Za-z]:[\\\\/]")) or (p | startswith("\\\\"))
        then (p | gsub("\\\\"; "/"))
        else p end;
      # "Claude Opus 5.5 (1M context)" -> "Opus 5.5". A display name without a
      # version ("Opus", as in the docs example) takes it from the id:
      # claude-opus-5-5 -> "Opus 5.5". The minor part is 1-2 digits, so a date
      # suffix (claude-sonnet-4-20250514) is never mistaken for a version.
      def shortname(n; id):
        if n == null or n == "" then "-"
        else (n | sub("^Claude "; "") | sub(" *\\(.*\\)$"; "")) as $s
          | if ($s | test("[0-9]")) then $s
            else ((id // "") | capture("^claude-[a-z]+-(?<a>[0-9]+)-(?<b>[0-9]{1,2})(?![0-9])")? // null) as $v
              | if $v == null then $s else "\($s) \($v.a).\($v.b)" end
            end
        end;
      [ dash(.model.id),
        shortname(.model.display_name; .model.id),
        ((.context_window.used_percentage // 0) | floor),
        (((.cost.total_cost_usd // 0) * 1000) | round),
        winnorm(.workspace.current_dir // .cwd),
        # Context window size, shown only when larger than the 200k default.
        (.context_window.context_window_size // 0 | floor
         | if . <= 200000 then "-"
           elif . % 1000000 == 0 then "\(. / 1000000 | floor)M"
           else "\(. / 1000 | floor)k" end),
        dash(.effort.level),
        (if (.fast_mode // false) then "1" else "0" end),
        pct(.rate_limits.five_hour.used_percentage),
        left(.rate_limits.five_hour.resets_at),
        pct(.rate_limits.seven_day.used_percentage),
        left(.rate_limits.seven_day.resets_at),
        (if .prompt_cache.hit_ratio == null then "-"
         else ((.prompt_cache.hit_ratio * 100) | round) end),
        (if .prompt_cache.warm == false then 0
         else left(.prompt_cache.expires_at) end),
        # Local additions (fields verified in a real Claude Code 2.1.323 payload).
        dash(.session_name),
        (.cost.total_lines_added // 0 | floor),
        (.cost.total_lines_removed // 0 | floor),
        ((.cost.total_duration_ms // 0) / 1000 | floor),
        ((.cost.total_api_duration_ms // 0) / 1000 | floor),
        (.context_window.total_input_tokens // 0 | floor),
        (.context_window.total_output_tokens // 0 | floor),
        (if .workspace.repo.owner == null then "-"
         else "\(.workspace.repo.owner)/\(.workspace.repo.name)" end),
        dash(.version)
      ] | @tsv' <<< "$input" 2>/dev/null) || parsed=""
fi

# jq on Windows can terminate the line with CRLF; a stray \r would land in the
# final field and fail the numeric guards below.
parsed=${parsed//$'\r'/}

if [ -n "$parsed" ]; then
    IFS=$'\t' read -r model_id model_display context_used cost_mills current_dir \
        ctx_size effort_level fast_mode five_h_pct five_h_left week_pct week_left \
        cache_pct cache_left \
        session_name lines_added lines_removed dur_s api_s tok_in tok_out repo_slug cc_version \
        <<< "$parsed"
    # @tsv doubles literal backslashes. Restore those pairs without printf %b,
    # which would interpret a Linux directory named test\name as a newline.
    current_dir=${current_dir//\\\\/\\}
else
    # No jq (or malformed input): recover just the directory from the raw JSON so
    # line 1 still says something useful. Allows optional spaces after the colon
    # and unescapes the doubled backslashes of a Windows path.
    d=$(printf '%s' "$input" \
        | grep -o '"current_dir"[[:space:]]*:[[:space:]]*"[^"]*"' \
        | head -1 \
        | sed 's/.*:[[:space:]]*"//; s/"$//') || d=""
    d=${d//$'\r'/}
    if [ -n "$d" ]; then
        # JSON doubles every backslash; for a Windows path collapse them straight
        # to forward slashes, matching what winnorm() does on the jq path.
        case "$d" in
            [A-Za-z]:*|'\\'*) d=${d//\\\\//}; d=${d//\\//} ;;
        esac
        current_dir="$d"
    fi
fi

# Guard every value that is used in arithmetic or compared numerically.
case "$context_used" in ''|*[!0-9]*) context_used=0 ;; esac
case "$cost_mills"   in ''|*[!0-9]*) cost_mills=0 ;; esac
[ "$context_used" -gt 100 ] && context_used=100

# ---------- Helpers (return through REPLY, no subshells) ----------
usage_color() {
    # $1 = integer percent -> more used is worse
    if   [ "$1" -ge 80 ]; then REPLY=$RED
    elif [ "$1" -ge 50 ]; then REPLY=$ORANGE
    else                       REPLY=$GREEN; fi
}

cache_color() {
    # $1 = integer percent -> higher is better. A long Claude Code session with a
    # stable prefix sits at 90%+; only the first requests (the initial cache
    # write) are naturally lower, so under 70% means repeated cache misses.
    if   [ "$1" -ge 90 ]; then REPLY=$GREEN
    elif [ "$1" -ge 70 ]; then REPLY=$ORANGE
    else                       REPLY=$RED; fi
}

fmt_left() {
    # $1 = seconds -> compact "3d4h" / "1h23m" / "60m" / "45m" / "<1m"
    # Up to 60 minutes stays in minutes: a fresh 1h cache reads "60m", not "1h00m".
    local s=$1 d h m
    d=$(( s / 86400 )); h=$(( (s % 86400) / 3600 )); m=$(( (s % 3600) / 60 ))
    if   [ "$d" -gt 0 ];    then printf -v REPLY '%dd%dh' "$d" "$h"
    elif [ "$s" -ge 3660 ]; then printf -v REPLY '%dh%02dm' "$h" "$m"
    elif [ "$s" -ge 60 ];   then REPLY="$(( s / 60 ))m"
    else                         REPLY='<1m'; fi
}

# ---------- LINE 1: git [worktree] | path ----------
norm=""
dir_display="N/A"
if [ "$current_dir" != "-" ] && [ -n "$current_dir" ]; then
    # Already separator-normalized by winnorm() in the jq call above; the
    # no-jq fallback normalizes its own value the same way.
    norm=${current_dir%/}
    if [ -z "$norm" ]; then
        dir_display="/"
    else
        dir_short=${norm##*/}
        parent_path=${norm%/*}
        parent_dir=${parent_path##*/}
        if [ -n "$parent_dir" ] && [ "$parent_path" != "$norm" ]; then
            dir_display="$parent_dir/$dir_short"
        else
            dir_display="$dir_short"
        fi
    fi
fi

# Ask git about the SESSION's directory, not whatever directory this script was
# started in. Let Git discover the repository itself: a lexical parent walk
# misses .git when the session directory is a symlink into a repository.
# A reported directory that does not exist here gets no branch, rather than the
# branch of whatever directory the script happens to run in.
git_branch=""
git_target="."
[ -n "$norm" ] && git_target="$norm"
if [ -d "$git_target" ]; then
    git_branch=$(git -C "$git_target" --no-optional-locks rev-parse --abbrev-ref HEAD 2>/dev/null) || git_branch=""
fi

# Local change: line 1 mirrors the Git for Windows PS1
#   user@host MSYSTEM path (branch)   in its colors (green, magenta, yellow, cyan).
# $USERNAME/$HOSTNAME/$MSYSTEM are shell variables, so no extra process is spawned.
PS1_GREEN="${E}[32m"; PS1_MAGENTA="${E}[35m"; PS1_YELLOW="${E}[33m"; PS1_CYAN="${E}[36m"
line1="${PS1_GREEN}${USERNAME:-${USER:-user}}@${HOSTNAME:-host}${RESET} ${PS1_MAGENTA}${MSYSTEM:-MINGW64}${RESET} ${PS1_YELLOW}${dir_display}${RESET}"
[ -n "$git_branch" ] && line1="${line1} ${PS1_CYAN}(${git_branch})${RESET}"
[ "${repo_slug:--}" != "-" ] && line1="${line1}${SEP}${DIM}${repo_slug}${RESET}"

# ---------- LINE 2: model | context | cost | usage | cache ----------
# Prefer the display name ("Opus 5.5"); fall back to the family from the id.
model_short="$model_display"
if [ "$model_short" = "-" ]; then
    case "$model_id" in
        *sonnet*)   model_short="Sonnet" ;;
        *opus*)     model_short="Opus" ;;
        *haiku*)    model_short="Haiku" ;;
        *fable*)    model_short="Fable" ;;
        *deepseek*) model_short="DeepSeek" ;;
        *glm*)      model_short="GLM" ;;
        *)          model_short="?" ;;
    esac
fi

model_part="${ACCENT}${model_short}${RESET}"
[ "$ctx_size" != "-" ] && model_part="${model_part} ${ACCENT}${ctx_size}${RESET}"
case "$effort_level" in
    -)     ;;
    max)   model_part="${model_part} ${RED}${effort_level}${RESET}" ;;
    xhigh) model_part="${model_part} ${ORANGE}${effort_level}${RESET}" ;;
    *)     model_part="${model_part} ${DIM}${effort_level}${RESET}" ;;
esac
[ "$fast_mode" = "1" ] && model_part="${model_part} ${ORANGE}Fast${RESET}"

# Progress bar for context
BAR_WIDTH=10
FILLED=$((context_used * BAR_WIDTH / 100))
EMPTY=$((BAR_WIDTH - FILLED))

BAR=""
if [ "$FILLED" -gt 0 ]; then
    printf -v FILL "%${FILLED}s" ""
    BAR="${BAR}${BAR_FILLED}${FILL// /▓}${RESET}"
fi
if [ "$EMPTY" -gt 0 ]; then
    printf -v PAD "%${EMPTY}s" ""
    BAR="${BAR}${BAR_EMPTY}${PAD// /░}${RESET}"
fi
context_part="$BAR ${FG}${context_used}%${RESET}"

# Real session cost, reported by Claude Code (cost.total_cost_usd).
# cost_mills is thousandths of a dollar, so all formatting stays integer-only.
cost_part=""
if [ "$cost_mills" -gt 0 ]; then
    cost_dollars=$((cost_mills / 1000))
    if [ "$cost_dollars" -gt 0 ]; then
        printf -v cost_formatted '~$%d.%02d' "$cost_dollars" "$(((cost_mills % 1000) / 10))"
    else
        printf -v cost_formatted '~$0.%03d' "$((cost_mills % 1000))"
    fi
    cost_part="${GOLD}${cost_formatted}${RESET}"
fi

# ---------- Subscription usage (5h + weekly) ----------
usage_part=""
case "$five_h_pct" in
    ''|*[!0-9]*) ;;
    *)  usage_color "$five_h_pct"
        seg="${REPLY}5h:${five_h_pct}%"
        case "$five_h_left" in
            ''|*[!0-9]*) ;;
            *) fmt_left "$five_h_left"; seg="${seg}(↻${REPLY})" ;;
        esac
        usage_part="${seg}${RESET}" ;;
esac
case "$week_pct" in
    ''|*[!0-9]*) ;;
    *)  usage_color "$week_pct"
        seg="${REPLY}7d:${week_pct}%"
        case "$week_left" in
            ''|*[!0-9]*) ;;
            *) fmt_left "$week_left"; seg="${seg}(↻${REPLY})" ;;
        esac
        usage_part="${usage_part:+$usage_part }${seg}${RESET}" ;;
esac

# ---------- Prompt cache: hit rate + time until it goes cold ----------
# "Cache: 96%(✕52m)" - ✕ marks when the cached prefix expires; the next request
# after that re-sends the whole context at full price. "(cold)" = already expired.
cache_part=""
case "$cache_pct" in
    ''|*[!0-9]*) ;;
    *)  cache_color "$cache_pct"
        seg="${REPLY}Cache: ${cache_pct}%"
        case "$cache_left" in
            ''|*[!0-9]*) ;;
            0) seg="${seg}${RED}(cold)" ;;
            *) fmt_left "$cache_left"
               # Under 5 minutes left: warn, whatever the hit rate.
               [ "$cache_left" -lt 300 ] && seg="${seg}${ORANGE}"
               seg="${seg}(✕${REPLY})" ;;
        esac
        cache_part="${seg}${RESET}" ;;
esac

if [ "$jq_missing" -eq 1 ]; then
    # Without jq there is no data to show, so say what to do about it rather
    # than rendering a row of meaningless zeroes.
    line2="${RED}jq not found${RESET}${DIM} - ask Claude to install jq${RESET}"
else
    line2="${model_part}${SEP}${context_part}"
    [ -n "$cost_part" ]  && line2="${line2}${SEP}${cost_part}"
    [ -n "$usage_part" ] && line2="${line2}${SEP}${usage_part}"
    [ -n "$cache_part" ] && line2="${line2}${SEP}${cache_part}"
fi

# ---------- OUTPUT ----------
# '%s' (not '%b'/echo -e): the colors are already real ESC bytes, so nothing in
# a path or branch name can be misread as an escape sequence.
# ---------- LINE 3 (local addition): session | lines | time | tokens | version ----------
fmt_tok() {
    # $1 = integer tokens -> "950" / "12.3k" / "1.2M" (integer math, locale-safe)
    local t=$1
    if   [ "$t" -ge 1000000 ]; then printf -v REPLY '%d.%dM' $(( t / 1000000 )) $(( (t % 1000000) / 100000 ))
    elif [ "$t" -ge 1000 ];    then printf -v REPLY '%d.%dk' $(( t / 1000 )) $(( (t % 1000) / 100 ))
    else                            REPLY="$t"; fi
}
for _v in lines_added lines_removed dur_s api_s tok_in tok_out; do
    case "${!_v:-}" in ''|*[!0-9]*) printf -v "$_v" '%s' 0 ;; esac
done
line3=""
[ "${session_name:--}" != "-" ] && line3="${ACCENT}${session_name}${RESET}"
lines_part="${GREEN}+${lines_added}${RESET}${DIM}/${RESET}${RED}-${lines_removed}${RESET}"
line3="${line3:+${line3}${SEP}}${lines_part}"
fmt_left "$dur_s"; dur_txt=$REPLY
fmt_left "$api_s"; api_txt=$REPLY
line3="${line3}${SEP}${FG}⏱ ${dur_txt}${RESET}${DIM} (API ${api_txt})${RESET}"
fmt_tok "$tok_in"; tin=$REPLY
fmt_tok "$tok_out"; tout=$REPLY
line3="${line3}${SEP}${FG}${tin} in${RESET}${DIM} / ${RESET}${FG}${tout} out${RESET}"
[ "${cc_version:--}" != "-" ] && line3="${line3}${SEP}${DIM}v${cc_version}${RESET}"

if [ "$jq_missing" -eq 1 ] || [ -z "$parsed" ]; then
    printf '%s\n%s\n' "$line1" "$line2"
else
    printf '%s\n%s\n%s\n' "$line1" "$line2" "$line3"
fi

# Always succeed - a non-zero exit blanks the status line.
exit 0
