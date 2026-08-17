import com.intellij.lexer.Lexer;
import com.intellij.lexer.MergingLexerAdapter;
import com.intellij.openapi.Disposable;
import com.intellij.openapi.application.Application;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.components.ComponentManager;
import com.intellij.openapi.extensions.ExtensionPoint;
import com.intellij.openapi.extensions.Extensions;
import com.intellij.openapi.extensions.impl.ExtensionsAreaImpl;
import com.intellij.psi.tree.IElementType;
import com.intellij.psi.tree.TokenSet;
import com.jetbrains.python.PyElementTypesFacade;
import com.jetbrains.python.PyElementTypesFacadeImpl;
import com.jetbrains.python.PyTokenTypes;
import com.jetbrains.python.PythonDialectsTokenSetContributor;
import com.jetbrains.python.PythonDialectsTokenSetProvider;
import com.jetbrains.python.lexer.PythonIndentingLexer;

import java.lang.reflect.Proxy;

/**
 * Instruments the lookahead the SageCaretLexer performs for every single `^`:
 * for each XOR token in the stream, restarts a scratch lexer at tokenEnd with
 * the delegate state and prints what the first token is.  Compares the
 * minimal file (clean) against the full test.sage (broken).
 */
public class TestLookahead {

  public static void main(String[] args) throws Exception {
    ComponentManager fakeManager = (ComponentManager)Proxy.newProxyInstance(
      ComponentManager.class.getClassLoader(),
      new Class<?>[]{ComponentManager.class},
      (proxy, method, a) -> defaultFor(method, proxy, a));
    ExtensionsAreaImpl area = new ExtensionsAreaImpl(fakeManager);
    Extensions.setRootArea(area);
    Disposable fakeDisposable = (Disposable)Proxy.newProxyInstance(
      Disposable.class.getClassLoader(), new Class<?>[]{Disposable.class}, (proxy, method, a) -> null);
    area.registerExtensionPoint(
      PythonDialectsTokenSetContributor.EP_NAME,
      PythonDialectsTokenSetContributor.EP_NAME.getName(),
      ExtensionPoint.Kind.INTERFACE,
      fakeDisposable);
    area.registerExtensionPoint("com.intellij.lang.ast.factory", "com.intellij.lang.ast.factory",
                                ExtensionPoint.Kind.INTERFACE, false);
    final PythonDialectsTokenSetProvider provider = new PythonDialectsTokenSetProvider();

    Application fakeApp = (Application)Proxy.newProxyInstance(
      Application.class.getClassLoader(),
      new Class<?>[]{Application.class},
      (proxy, method, a) -> {
        if (method.getName().equals("getService") && a.length == 1 &&
            a[0] == PythonDialectsTokenSetProvider.class) return provider;
        if (method.getName().equals("getService") && a.length == 1 &&
            a[0] == PyElementTypesFacade.class) return new PyElementTypesFacadeImpl();
        if (method.getName().equals("getExtensionArea")) return area;
        return defaultFor(method, proxy, a);
      });
    ApplicationManager.setApplication(fakeApp);

    String minimal = "m = 1\nn = 1\nm ^^=1\nprint(m)\n";
    String full =
      "# c\nfrom six import byte2int, int2byte\n\nR.<x> = GF(2)[]\nF.<a> = GF(2^8, modulus=x^8 + x^4 + x^3 + x + 1)\n\n" +
      "e = F.from_integer(0x57)\nprint('e =', e, '|', e.to_integer(), '|', e.polynomial())\n" +
      "b = F.from_integer(0x83)\nprint('0x57 * 0x83 =', e * b, '|', (e * b).to_integer() == 0xC1)\n" +
      "print('a + b =', a + b, '| a - b =', a - b, '| a / b =', a / b)\n" +
      "m = 1\nn = 1\nm ^^=1\nprint(m)\n\n\n" +
      "print('ei =', e^(-1), '| e^254 =', e^254, '|', e^(-1) == e^254)\n" +
      "print('x o =', a.multiplicative_order(), '(51)')\n\ng = F.multiplicative_generator()\n" +
      "print('g =', g, '| log_g(e) =', e.log(g), '|', g^e.log(g) == e)\n\n" +
      "print('c:', F.characteristic(), '| n:', F.order())\nprint('modulus:', F.modulus())\nprint('r:', F.random_element())\n";

    for (String[] c : new String[][]{{"minimal", minimal}, {"full", full}}) {
      System.out.println("=== " + c[0]);
      instrument(c[1]);
    }
  }

  static void instrument(String text) {
    MergingLexerAdapter delegate = new MergingLexerAdapter(
      new PythonIndentingLexer(), TokenSet.create(PyTokenTypes.XOR));
    // Same single scratch instance reused across lookaheads, exactly like
    // SageCaretLexer.myAhead.
    MergingLexerAdapter scratch = new MergingLexerAdapter(
      new PythonIndentingLexer(), TokenSet.create(PyTokenTypes.XOR));
    delegate.start(text, 0, text.length(), 0);
    while (true) {
      IElementType t = delegate.getTokenType();
      if (t == null) break;
      int s = delegate.getTokenStart();
      int e = delegate.getTokenEnd();
      if (t == PyTokenTypes.XOR || TokenSet.create(PyTokenTypes.XOR).contains(t)) {
        String tok = text.substring(s, e).replace("\n", "\\n");
        int state = delegate.getState();
        scratch.start(text, e, text.length(), state);
        IElementType first = scratch.getTokenType();
        String firstText = first == null ? "<null>" :
          text.substring(scratch.getTokenStart(), scratch.getTokenEnd()).replace("\n", "\\n");
        System.out.println(String.format("  XOR [%d-%d] '%s' len=%d state=%d -> first='%s' (%s)",
                                         s, e, tok, e - s, state, firstText, first));
      }
      delegate.advance();
    }
  }

  static Object defaultFor(java.lang.reflect.Method method, Object proxy, Object[] a) {
    if (method.getName().equals("toString")) return "Fake";
    if (method.getName().equals("hashCode")) return System.identityHashCode(proxy);
    if (method.getName().equals("equals")) return proxy == a[0];
    Class<?> rt = method.getReturnType();
    if (rt == boolean.class) return false;
    if (rt == int.class) return 0;
    if (rt == long.class) return 0L;
    if (rt == char.class) return '\0';
    return null;
  }
}
