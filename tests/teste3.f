C =========================================================
C TESTE 3 - IF THEN / ELSEIF / ELSE
C =========================================================
      PROGRAM IFBLK
      INTEGER N
      N = 0
      IF (N .LT. 0) THEN
          PRINT *, 'NEG'
      ELSEIF (N .EQ. 0) THEN
          PRINT *, 'ZERO'
      ELSE
          PRINT *, 'POS'
      ENDIF
      END