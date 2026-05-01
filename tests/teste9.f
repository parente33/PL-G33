C =========================================================
C TESTE 9 - SUBROUTINE + CALL
C =========================================================
      PROGRAM CALLSUB
      INTEGER A
      A = 5
      CALL MOSTRA(A)
      END

      SUBROUTINE MOSTRA(V)
      INTEGER V
      PRINT *, 'VALOR=', V
      RETURN
      END