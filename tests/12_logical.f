C =========================================================
C TESTE 12 - LOGICOS
C =========================================================
      PROGRAM LOGIC
      LOGICAL A, B
      A = .TRUE.
      B = .FALSE.
      IF (A .AND. .NOT. B) THEN
          PRINT *, 'OK'
      ENDIF
      END