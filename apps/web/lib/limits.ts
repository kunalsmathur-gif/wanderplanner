/**
 * Input length caps, mirroring `apps/api/core/validation.py`.
 *
 * These deliberately match the backend numbers rather than being stricter.
 * A frontend cap that is tighter than the server's would silently truncate
 * something the API would have accepted (`maxLength` drops the extra
 * keystrokes without saying so), and one that is looser lets a user type a
 * value that can only fail at submit. Change these together with the Python
 * constants, or not at all.
 */

export const MAX_CITY_LEN = 80
export const MAX_COUNTRY_LEN = 80
export const MAX_LABEL_LEN = 60
export const MAX_PURPOSE_LEN = 200
export const MAX_CHAT_MESSAGE_LEN = 4000
export const MAX_EXTRACT_INPUT_LEN = 8000
export const MAX_SEARCH_QUERY_LEN = 200

/** models/auth.py — SignupRequest / ResetPasswordRequest. */
export const MAX_PASSWORD_LEN = 128
export const MAX_DISPLAY_NAME_LEN = 120
/** RFC 5321's maximum total email address length. */
export const MAX_EMAIL_LEN = 254

/** Local-only booking notes (bookingStore), never sent to the API. */
export const MAX_BOOKING_NAME_LEN = 120
export const MAX_BOOKING_REF_LEN = 60
