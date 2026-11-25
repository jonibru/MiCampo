-- Solo desarrollo local: se ejecuta con `supabase db reset`. No se aplica a la nube.
-- En la nube, el login del rol micampo_app se configura a mano (ver backend/README.md).
alter role micampo_app login password 'micampo_local';
