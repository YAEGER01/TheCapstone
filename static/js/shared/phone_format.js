/*
 * Shared Philippine mobile-number formatter.
 *
 * Every phone field in the app displays ONE canonical format — 09##-###-#### —
 * no matter how the member types it:
 *
 *   09171234567      -> 0917-123-4567
 *   0917-123-4567    -> 0917-123-4567
 *   +639171234567    -> 0917-123-4567
 *   639171234567     -> 0917-123-4567
 *   69171234567      -> 0917-123-4567   (bare "6" treated as a +63 seed)
 *
 * While the country-code seed is still being typed the raw prefix stays on
 * screen ("+63", "63", "6") so the caret never eats the user's keystrokes;
 * the moment subscriber digits exist everything collapses to the 09## shape.
 */
(function () {
  "use strict";

  var GROUP_SIZES = [4, 3, 4]; // 09## - ### - ####
  var MAX_DIGITS = 11; // 0 + 9 + 9 digits

  function digitsOnly(value) {
    return String(value == null ? "" : value).replace(/\D/g, "");
  }

  function isIntlSeed(raw, digits) {
    return /^\s*\+/.test(String(raw == null ? "" : raw)) ||
      digits.indexOf("63") === 0 ||
      digits.indexOf("6") === 0;
  }

  /*
   * Reduce whatever the user typed to the bare 11-digit national number
   * (09171234567). Returns "" for an empty field. An incomplete country-code
   * seed returns that seed verbatim ("+", "+6", "+63", "6", "63") so typing
   * is never swallowed; once subscriber digits exist everything collapses to
   * the 09## shape, including numbers typed without their trunk 0.
   */
  function normalizeNational(raw) {
    var typed = digitsOnly(raw);
    if (!typed) {
      // Keep a lone "+" so the user can see they are in international mode.
      return /^\s*\+/.test(String(raw == null ? "" : raw)) ? "+" : "";
    }

    if (isIntlSeed(raw, typed)) {
      var core = typed;
      if (core.indexOf("63") === 0) core = core.slice(2);
      else if (core.indexOf("6") === 0) core = core.slice(1);
      if (!core.length) {
        // Country code only so far — show it back and wait for more digits.
        return /^\s*\+/.test(String(raw == null ? "" : raw))
          ? "+" + typed.slice(0, MAX_DIGITS)
          : typed.slice(0, MAX_DIGITS);
      }
      if (core.charAt(0) !== "0") core = "0" + core;
      return core.slice(0, MAX_DIGITS);
    }

    // Local entry — complete a missing trunk 0 so the display never drifts
    // away from 09##-###-####.
    if (typed.charAt(0) !== "0") typed = "0" + typed;
    return typed.slice(0, MAX_DIGITS);
  }

  function formatNational(national) {
    var d = String(national || "");
    if (!d) return "";
    var parts = [];
    var i = 0;
    for (var g = 0; g < GROUP_SIZES.length; g++) {
      if (i >= d.length) break;
      parts.push(d.slice(i, i + GROUP_SIZES[g]));
      i += GROUP_SIZES[g];
    }
    return parts.join("-");
  }

  function countDigits(text) {
    return digitsOnly(text).length;
  }

  /* Place the caret after the n-th digit of a formatted string. */
  function caretAfterDigits(text, n) {
    if (n <= 0) return 0;
    var seen = 0;
    for (var i = 0; i < text.length; i++) {
      if (text[i] >= "0" && text[i] <= "9") {
        seen++;
        if (seen === n) return i + 1;
      }
    }
    return text.length;
  }

  /* Format a value without touching the DOM — useful for stored records. */
  function format(value) {
    return formatNational(normalizeNational(value));
  }

  /* Digits as stored/validated by the backend: 09171234567. */
  function digits(value) {
    return digitsOnly(normalizeNational(value));
  }

  function isValid(value) {
    return /^09\d{9}$/.test(digits(value));
  }

  /*
   * Live formatter: rewrites the input on every keystroke and keeps the caret
   * anchored to the same digit, so typing anywhere in the number works.
   */
  function attach(input) {
    if (!input || input.__phoneFormatBound) return input;
    input.__phoneFormatBound = true;
    input.setAttribute("inputmode", "tel");
    input.addEventListener("input", function () {
      var caret = input.selectionStart;
      if (caret == null) caret = input.value.length;
      // Digits typed before the caret, already reduced to national form.
      var digitsBefore = countDigits(normalizeNational(input.value.slice(0, caret)));
      var formatted = format(input.value);
      var atEnd = caret >= input.value.length;
      input.value = formatted;
      var pos = atEnd ? formatted.length : caretAfterDigits(formatted, digitsBefore);
      try {
        input.setSelectionRange(pos, pos);
      } catch (e) {}
    });
    if (input.value) input.value = format(input.value);
    return input;
  }

  window.PHONE_FORMAT = {
    attach: attach,
    format: format,
    digits: digits,
    isValid: isValid,
    normalizeNational: normalizeNational,
  };
})();
