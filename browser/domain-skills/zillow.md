---
domain: zillow.com
last_verified: 2026-08-12
auth: operator Zillow Rental Manager account
browser: CloakBrowser persistent profile
---

# Zillow Rental Manager

## Required browser path

- Use CloakBrowser `launch_persistent_context`; never plain Playwright or an ephemeral context.
- Local profile: `%USERPROFILE%\.oasis\zillow-cloak-session.profile`.
- Use a headed browser for login/2FA and production runs.
- Current stealth verification: 5/5 signals pass without a proxy on CCPC.
- A plain/persistent Google Chrome profile can return the outer HTML with status 200 while `rental-manager-api/ws/services` returns 403 and the application body stays empty.
- Classify a zero-text Rental Manager body as `empty_shell`, never authenticated.

## Verified Properties page

- URL: `https://www.zillow.com/rental-manager/properties`
- Ready signals: exact text `Properties` and exact button `Add a property`.
- Challenge signals: text containing `verification code`, `verify your identity`, or `security code`.
- Account menu currently exposes the signed-in brokerage account name; do not store that value in automation artifacts.

## Verified Add Property modal

Captured live from the authenticated account on 2026-08-12.

- Heading: `First, let’s add your property`
- Street address: label text `Street address`; USPS validation applies and the address cannot be edited after creation.
- Property type: combobox with accessible name `Property type` and placeholder `Select property type`.
- Unit: textbox with accessible name `Unit number`.
- Room-for-rent checkbox id: `LabeledControl-roomForRent`; prefer its visible label rather than the id.
- Mutation button: exact role/button name `Create listing`.
- Safe exit: exact role/button name `Close` within the modal.

## Approval gates

- Opening the Add Property modal is navigation and safe for mapping.
- `Create listing` creates a real Zillow property record and requires CC approval.
- The later wizard `Publish` button requires a separate final approval after the worker reaches Review.
- Original ordered photos go to Zillow; the rendered video is organic-social-only.

## Production transport decision

- A live authenticated CCPC test on 2026-08-12 triggered a visible PerimeterX
  `Press & Hold` challenge on the first automated address-field interaction.
- Do not use browser form filling as an unattended production publisher and do
  not automate the challenge. CloakBrowser is diagnostic/read-only for Zillow.
- Preferred transport: Zillow Rentals Feed Integration after Zillow approval and
  certification. Interim transport: a human-assisted packet and deep link.
- The Bridge MLS Listings API is read access to MLS-authorized data, not a
  rental publishing API.

## Known workflow pages from live operator evidence

`Property info → Rent details → Media → Amenities → Screening criteria → Costs & fees → Final details → Review → Publish`

Do not claim selectors for pages after Add Property until the controlled production draft has reached them and they have been captured from the live DOM.
