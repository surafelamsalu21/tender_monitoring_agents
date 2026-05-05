"""
Email notification HTTP routes are implemented on the system router:

  GET/POST  /api/v1/system/email-settings
  POST      /api/v1/system/email-settings/{category}/add
  DELETE    /api/v1/system/email-settings/{category}/{email}
  POST      /api/v1/system/test-email

This module is kept as a pointer for older references; it does not register routes.
"""
