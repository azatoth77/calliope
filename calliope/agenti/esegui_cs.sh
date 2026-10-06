#!/bin/sh
# Compila ed esegue un programma C# dentro il container della sandbox (04/10/2026,
# setup/linux/sandbox/Dockerfile.dotnet). Non si lancia a mano: lo monta in sola lettura
# calliope/agenti/sandbox.py, come _avvio.py per Python.
#
#   sh esegui_cs.sh <cartella relativa del programma> [argomenti…]
#
# Compila tutti i file .cs di quella cartella (non delle sottocartelle) con csc, senza
# MSBuild né NuGet (niente rete), poi esegue il programma con gli argomenti. Lo stdin è
# quello del container. Gli errori di compilazione vanno sullo stderr, con una riga finale
# riconoscibile; il codice d'uscita è quello del compilatore o del programma.
set -u
cartella="/lavoro/${1:-.}"
shift
uscita=/lavoro/.tmp/cs
rm -rf "$uscita" && mkdir -p "$uscita" || exit 70
find "$cartella" -maxdepth 1 -type f -name '*.cs' -printf '"%p"\n' | sort > "$uscita/file.rsp"
if [ ! -s "$uscita/file.rsp" ]; then
  echo "— nessun file .cs da compilare —" >&2
  exit 2
fi
dotnet /opt/csc/csc.dll -nologo -target:exe -langversion:latest -nullable:enable \
  -optimize+ -deterministic -warn:1 -out:"$uscita/programma.dll" \
  @/opt/csc/riferimenti.rsp /opt/csc/usings.cs @"$uscita/file.rsp" >&2
codice=$?
if [ "$codice" -ne 0 ]; then
  echo "— compilazione non riuscita —" >&2
  exit "$codice"
fi
printf '%s' '{"runtimeOptions":{"tfm":"net10.0","framework":{"name":"Microsoft.NETCore.App","version":"10.0.0"},"rollForward":"LatestMinor"}}' \
  > "$uscita/programma.runtimeconfig.json"
exec dotnet "$uscita/programma.dll" "$@"
