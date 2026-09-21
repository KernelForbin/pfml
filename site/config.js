/* Supabase project for the members-only site.
   Both values are public by design: the publishable key can only do what
   the row level security rules in supabase/schema.sql allow, which for a
   visitor who isn't a linked member is nothing. NEVER put the secret key
   (sb_secret_...) here: it bypasses those rules, and this file is public. */
window.PFML_CONFIG = {
  supabaseUrl: "https://usdyarwpvsxkkwqibdpt.supabase.co",
  supabasePublishableKey: "sb_publishable_Jg1B92IarRL2cVdCqJUuMA_UsU5QqUV"
};
